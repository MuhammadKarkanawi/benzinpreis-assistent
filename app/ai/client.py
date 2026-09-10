"""
Dünner Client für einen lokal betriebenen, OpenAI-kompatiblen Inference-
Server (z.B. Ollama, llama.cpp server, LM Studio).

Bewusst ohne Abhängigkeit vom `openai`-Python-Paket implementiert (nur
`httpx`), damit exakt nachvollziehbar ist, welche HTTP-Schnittstelle
angesprochen wird (POST {base_url}/chat/completions) - das ist der Vertrag,
den alle oben genannten Server erfüllen.

Fehlerbehandlung (Anforderung: nicht erreichbar / Timeout / ungültige
Ausgabe müssen behandelt werden):
- AIUnavailableError: Server nicht erreichbar (Connection refused/DNS/etc.)
- AITimeoutError: Zeitüberschreitung
- AIInvalidResponseError: Antwort nicht im erwarteten Format
"""
from __future__ import annotations

import httpx

from app.config import Settings


class AIClientError(Exception):
    """Basisklasse für alle Fehler der KI-Komponente."""


class AIUnavailableError(AIClientError):
    pass


class AITimeoutError(AIClientError):
    pass


class AIInvalidResponseError(AIClientError):
    pass


class AIClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        """`transport` erlaubt das Injizieren eines httpx.MockTransport in
        automatisierten Tests, ohne einen echten Server zu starten."""
        self._settings = settings
        self._transport = transport

    async def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        """Sendet eine Chat-Completion-Anfrage und gibt den reinen Antworttext
        zurück. Wirft eine der oben definierten Exceptions bei Problemen."""
        url = f"{self._settings.ai_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._settings.ai_model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self._settings.ai_api_key}"}

        last_error: Exception | None = None
        attempts = max(1, self._settings.ai_max_retries + 1)
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=self._settings.ai_timeout_seconds, transport=self._transport
                ) as client:
                    response = await client.post(url, json=payload, headers=headers)
                if response.status_code >= 500:
                    last_error = AIUnavailableError(
                        f"Inference-Server antwortete mit Status {response.status_code}"
                    )
                    continue
                if response.status_code >= 400:
                    raise AIInvalidResponseError(
                        f"Inference-Server lehnte Anfrage ab (Status {response.status_code}): {response.text[:300]}"
                    )
                data = response.json()
                return self._extract_content(data)
            except httpx.TimeoutException as exc:
                last_error = AITimeoutError(f"Zeitüberschreitung beim Aufruf des Inference-Servers: {exc}")
            except httpx.ConnectError as exc:
                last_error = AIUnavailableError(f"Inference-Server nicht erreichbar unter {url}: {exc}")
            except httpx.HTTPError as exc:
                last_error = AIUnavailableError(f"HTTP-Fehler beim Aufruf des Inference-Servers: {exc}")

        assert last_error is not None
        raise last_error

    @staticmethod
    def _extract_content(data: dict) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIInvalidResponseError(f"Unerwartetes Antwortformat vom Inference-Server: {data!r}") from exc
        if not isinstance(content, str) or not content.strip():
            raise AIInvalidResponseError("Inference-Server lieferte leere oder ungültige Antwort.")
        return content.strip()
