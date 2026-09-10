"""Orchestriert die Beantwortung einer Nutzerfrage:

1. Fakten aus der deterministischen Logik sammeln (grounding.py).
2. Prompt bauen (prompts.py).
3. Lokales Sprachmodell aufrufen (client.py) - mit Fehlerbehandlung.
4. Antwort auf Groundedness prüfen (validation.py).
5. Anfrage + Antwort persistieren (QueryLog).
"""
from __future__ import annotations

import json
import time

from sqlmodel import Session

from app.ai.client import AIClient, AIClientError
from app.ai.grounding import NoDataForStationError, gather_facts
from app.ai.prompts import build_messages
from app.ai.validation import is_grounded
from app.config import Settings
from app.models import QueryLog


async def answer_question(
    session: Session,
    settings: Settings,
    ai_client: AIClient,
    station_uuid: str,
    fuel_type: str,
    question: str,
    use_context: bool = True,
) -> dict:
    start = time.perf_counter()

    facts: dict | None = None
    error: str | None = None
    answer_text = ""
    flagged = False

    try:
        if use_context:
            facts = gather_facts(session, settings, station_uuid, fuel_type)
        messages = build_messages(question, facts if use_context else None)
        answer_text = await ai_client.chat(messages)
        flagged = not is_grounded(answer_text, facts if use_context else None)
    except NoDataForStationError as exc:
        error = str(exc)
    except AIClientError as exc:
        error = str(exc)
        answer_text = (
            "Die KI-Komponente ist gerade nicht erreichbar oder hat keine gültige Antwort geliefert. "
            "Bitte später erneut versuchen."
        )

    latency_ms = (time.perf_counter() - start) * 1000

    log = QueryLog(
        station_uuid=station_uuid,
        question=question,
        grounding_facts_json=json.dumps(facts, ensure_ascii=False) if facts else "{}",
        answer=answer_text,
        used_context=use_context,
        error=error,
        latency_ms=latency_ms,
        flagged_ungrounded=flagged,
    )
    session.add(log)
    session.commit()

    return {
        "answer": answer_text,
        "used_context": use_context,
        "grounding_facts": facts or {},
        "flagged_ungrounded": flagged,
        "latency_ms": round(latency_ms, 1),
        "model": settings.ai_model,
        "error": error,
    }
