# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# System-Abhängigkeiten (schlank halten)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY mock_llm_server ./mock_llm_server
COPY scripts ./scripts
COPY data ./data

# Läuft als unprivilegierter Nutzer
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Standard: die eigentliche Anwendung. Für den Mock-LLM-Server wird in
# docker-compose.yml derselbe Image mit anderem Kommando verwendet.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
