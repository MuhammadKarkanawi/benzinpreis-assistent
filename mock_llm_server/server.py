"""
Kleiner, deterministischer Stand-in-Server, der die OpenAI-kompatible
/v1/chat/completions-Schnittstelle nachbildet (kein echtes Sprachmodell).

Zweck: In Umgebungen ohne Zugriff auf einen echten lokalen Inference-Server
(z.B. dieser Cloud-Entwicklungs-Workspace ohne Netzwerkzugriff auf
Ollama/Hugging Face) kann die Anwendung trotzdem vollständig End-to-End
demonstriert, automatisiert getestet und ausgewertet werden.

WICHTIG: Dies ist KEIN Ersatz für die geforderte echte lokale KI-Komponente.
Für die tatsächliche Abgabe/Bewertung muss ein echter lokaler Inference-
Server (Ollama, llama.cpp, LM Studio, ...) mit einem echten Modell laufen
(siehe README). Dieser Mock dient nur der Entwicklung, den automatisierten
Tests und als Fallback-Profil in docker-compose, damit der Service auch
"out of the box" ohne GPU/Modell-Download startet.

Verhalten: Liest die im Prompt eingebetteten FAKTEN (JSON) und formuliert
eine einfache, regelbasierte deutsche Antwort ausschließlich auf Basis
dieser Zahlen. Ohne FAKTEN (ungrounded-Modus) antwortet er ehrlich, dass
keine Daten vorliegen. Bei erkennbar themenfremden Fragen lehnt er ab.
"""
from __future__ import annotations

import json
import re
import time

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock OpenAI-compatible LLM server (Testzwecke)")

OFF_TOPIC_KEYWORDS = [
    "aktie", "aktien", "börse", "bitcoin", "krypto", "gold kaufen",
    "wetter", "fußball", "rezept", "programmier",
]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None


def _extract_facts(messages: list[ChatMessage]) -> dict | None:
    for m in messages:
        if m.role == "user" and "FAKTEN:" in m.content:
            match = re.search(r"FAKTEN:\s*(\{.*?\})\s*\n\nFRAGE", m.content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    return None
    return None


def _question_text(messages: list[ChatMessage]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            if "FRAGE:" in m.content:
                return m.content.split("FRAGE:", 1)[1].strip()
            return m.content
    return ""


def _looks_off_topic(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in OFF_TOPIC_KEYWORDS)


LONG_HORIZON_KEYWORDS = ["jahr", "jahren", "monat", "monaten", "jahre"]
GERMAN_QUESTION_MARKERS = [
    "wie", "was", "wann", "wird", "ist", "soll", "lohnt", "bist", "sind", "kann",
    "günstiger", "teurer", "preis", "tanken", "fallen", "steigen", "sicher",
]
OTHER_FUEL_KEYWORDS = ["e10", "e5", "diesel", "super"]


def _looks_unclear(question: str) -> bool:
    q = question.lower()
    tokens = [t.strip("?!.,;: ") for t in q.split()]
    if not tokens:
        return True
    recognized = sum(1 for t in tokens if any(marker in t for marker in GERMAN_QUESTION_MARKERS))
    return recognized == 0


def generate_reply(messages: list[ChatMessage]) -> str:
    question = _question_text(messages)
    facts = _extract_facts(messages)
    q_lower = question.lower()

    if _looks_off_topic(question):
        return (
            "Dazu kann ich leider nichts sagen - ich bin nur für Kraftstoffpreise "
            "dieser Tankstelle zuständig."
        )

    if facts is None:
        return (
            "Mir liegen für diese Anfrage keine aktuellen Daten vor, daher kann ich "
            "dazu keine konkreten Zahlen nennen."
        )

    if any(kw in q_lower for kw in LONG_HORIZON_KEYWORDS):
        horizon = (facts.get("forecast") or {}).get("horizon_hours", "wenige")
        return (
            f"Dafür liegt mir keine verlässliche Grundlage vor: meine Vorhersage deckt nur "
            f"einen Horizont von {horizon} Stunden ab, keine Monate oder Jahre."
        )

    if _looks_unclear(question):
        return "Deine Frage ist für mich nicht eindeutig - kannst du sie zu Preis, Vorhersage oder Tankzeit konkretisieren?"

    other_prices = facts.get("other_current_prices_eur") or {}
    mentioned_other = [f for f in OTHER_FUEL_KEYWORDS if f in q_lower and f != facts.get("fuel_type")]
    if mentioned_other and other_prices:
        this_price = facts.get("current_price_eur")
        lines = [f"{facts.get('fuel_type')}: {this_price:.3f} EUR"]
        for fuel, price in other_prices.items():
            lines.append(f"{fuel}: {price:.3f} EUR")
        return "Aktueller Vergleich - " + ", ".join(lines) + "."

    parts = []
    price = facts.get("current_price_eur")
    if price is not None:
        parts.append(f"Der aktuelle Preis liegt bei {price:.3f} EUR.")

    forecast = facts.get("forecast")
    if forecast:
        direction = forecast.get("direction")
        predicted = forecast.get("predicted_price_eur")
        confidence = forecast.get("confidence_heuristic_0_to_1")
        if direction and predicted is not None:
            parts.append(
                f"Nach bisherigem Muster wird der Preis in den nächsten "
                f"{forecast.get('horizon_hours', '?')} Stunden voraussichtlich {direction} "
                f"sein (geschätzt {predicted:.3f} EUR, Vertrauenswert ca. {confidence})."
            )

    window = facts.get("best_refuel_window")
    if window:
        parts.append(
            f"Ein historisch günstiges Zeitfenster liegt zwischen {window.get('start')} "
            f"und {window.get('end')} (erwartet ca. {window.get('expected_price_eur'):.3f} EUR)."
        )

    if not parts:
        return "Dazu liegen mir aktuell keine ausreichenden Daten vor."

    return " ".join(parts)


@app.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest):
    reply = generate_reply(request.messages)
    return {
        "id": "mock-completion",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
    }


@app.get("/v1/models")
def list_models():
    return {"data": [{"id": "mock-model", "object": "model"}]}
