# Benzinpreis-Assistent

Ein Dienst, der historische Kraftstoffpreise einer Tankstelle analysiert,
eine kurzfristige Preisvorhersage sowie eine "beste Tankzeit"-Empfehlung
berechnet - beides mit **deterministischer, nicht-KI-basierter** Logik - und
Nutzerfragen dazu über eine **lokal betriebene, gegründete (grounded)**
KI-Komponente beantwortet, die ausschließlich auf Basis dieser berechneten
Fakten antwortet.

Projektkontext: Studienprojekt im Modul "AI Software Engineering" (TU
Dortmund, Prof. Falk Howar). Anforderungen siehe Aufgabenstellung
("AISE Project: Building AI-Enabled Software with AI Agents").

## Kurzbeschreibung (eine Zeile)

> Der Dienst berechnet Preistrends und Tankzeit-Empfehlungen für eine
> Tankstelle und erklärt sie auf Nachfrage in natürlicher Sprache - streng
> auf Basis der tatsächlich berechneten Zahlen, nie erfunden.

## Architekturüberblick

```
┌─────────────────────┐      ┌──────────────────────────┐
│   Weboberfläche      │◄────►│   FastAPI-Anwendung       │
│  (app/static/*.html) │      │   (app/main.py + Router)  │
└─────────────────────┘      └───────────┬──────────────┘
                                           │
                     ┌─────────────────────┼─────────────────────┐
                     ▼                     ▼                     ▼
          ┌────────────────────┐ ┌──────────────────┐ ┌───────────────────────┐
          │ Nicht-KI-Kernlogik  │ │  Persistenz       │ │  KI-Komponente         │
          │ app/forecasting.py  │ │  SQLite/SQLModel  │ │  app/ai/*              │
          │ (Trend, Saisonalität,│ │  (Station,       │ │  - grounding.py         │
          │  Tankzeit-Empfehlung)│ │  PriceRecord,     │ │    (sammelt Fakten aus  │
          └────────────────────┘ │  ForecastResult,  │ │     Kernlogik + DB)     │
                                  │  QueryLog)        │ │  - prompts.py           │
                                  └──────────────────┘ │  - client.py (HTTP zu    │
                                                        │    OpenAI-kompatiblem   │
                                                        │    lokalem Server)      │
                                                        │  - validation.py         │
                                                        │    (Groundedness-Check) │
                                                        └────────────┬────────────┘
                                                                     ▼
                                                     ┌───────────────────────────────┐
                                                     │ Lokaler Inference-Server        │
                                                     │ (Ollama / llama.cpp / LM Studio  │
                                                     │  ODER mock_llm_server/ zum       │
                                                     │  Testen ohne echtes Modell)      │
                                                     └───────────────────────────────┘
```

**Datenfluss einer Frage** (`POST /ask`): Fakten aus Forecasting+DB sammeln
→ strikten Prompt bauen ("nutze NUR diese Zahlen") → lokales Modell aufrufen
→ Antwort auf erfundene Zahlen prüfen → Frage+Antwort+Flag in `QueryLog`
speichern → Antwort zurückgeben.

## Warum diese Trennung?

Die Vorhersage- und Empfehlungslogik (Kern des Nutzens) ist bewusst
**deterministisch und ohne LLM** implementiert - sie muss testbar,
nachvollziehbar und reproduzierbar sein. Das LLM wird ausschließlich für die
Formulierung natürlichsprachlicher Erklärungen eingesetzt und darf laut
System-Prompt keine eigenen Zahlen erfinden (RAG-artiges "Grounding"). Eine
automatisierte Heuristik (`app/ai/validation.py`) prüft das im laufenden
Betrieb.

## Setup

### Voraussetzungen

- Python 3.11+
- Docker + Docker Compose (für containerisierte Ausführung)
- Ein lokaler, OpenAI-kompatibler Inference-Server für die echte KI-Komponente,
  z.B. [Ollama](https://ollama.com):
  ```bash
  ollama pull gemma3n:e4b
  ollama serve   # stellt eine OpenAI-kompatible API unter http://localhost:11434/v1 bereit
  ```

### Lokal ohne Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Beispieldaten erzeugen (einmalig; siehe "Beispieldaten" unten)
python -m scripts.generate_sample_data

cp .env.example .env
# .env anpassen: AI_BASE_URL/AI_MODEL auf den eigenen Inference-Server setzen

uvicorn app.main:app --reload
# → http://localhost:8000  (Dashboard), http://localhost:8000/docs (OpenAPI/Swagger)
```

Ohne laufenden Inference-Server startet die Anwendung trotzdem: Preisverlauf,
Vorhersage und Tankzeit-Empfehlung funktionieren unverändert, nur `/ask`
liefert einen kontrollierten Fehler und `/health` meldet
`ai_backend_reachable: false` (siehe Anforderung "Failure handling").

### Mit Docker Compose

```bash
cp .env.example .env

# Variante A: mit dem mitgelieferten Mock-KI-Server (kein Modell-Download nötig, nur Demo/Test):
AI_BASE_URL=http://mock-ai:8100/v1 AI_MODEL=mock-model \
  docker compose --profile mock up --build

# Variante B: mit echtem lokalem Modell über Ollama:
AI_BASE_URL=http://ollama:11434/v1 AI_MODEL=gemma3n:e4b \
  docker compose --profile real up --build
# einmalig zusätzlich, in einem zweiten Terminal:
docker compose exec ollama ollama pull gemma3n:e4b
```

`docker compose up app` (ohne Profil) startet den Dienst auch ganz allein -
degradiert (ohne KI-Antwortfunktion), aber lauffähig.

> **Hinweis zur Entstehung:** Dieses Projekt wurde in einem Cloud-Entwicklungs-
> Workspace mit eingeschränktem Netzwerkzugriff entwickelt (kein Zugriff auf
> Docker Hub/Ollama/Hugging Face, siehe `AI_DEVELOPMENT_LOG.md`, Episode 5).
> Dockerfile/docker-compose.yml sind syntaktisch geprüft
> (`docker compose config`), aber **nicht** in dieser Umgebung build-getestet
> worden. Bitte vor der Abgabe einmal real ausführen und verifizieren.

## Konfiguration

Alle Werte sind über Umgebungsvariablen konfigurierbar (siehe `.env.example`
und `app/config.py`):

| Variable | Bedeutung | Beispiel |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy-Datenbank-URL | `sqlite:///./data/app.db` |
| `AI_BASE_URL` | Basis-URL des OpenAI-kompatiblen Inference-Servers | `http://localhost:11434/v1` |
| `AI_MODEL` | Modellname/-tag beim Inference-Server | `gemma3n:e4b` |
| `AI_API_KEY` | API-Key (bei rein lokalem Betrieb meist irrelevant) | `not-needed-for-local-inference` |
| `AI_TIMEOUT_SECONDS` | Timeout je Anfrage an das Modell | `20` |
| `AI_MAX_RETRIES` | Zusätzliche Versuche bei 5xx-Antworten | `1` |
| `FORECAST_HORIZON_HOURS` | Standard-Vorhersagehorizont | `24` |
| `MIN_HISTORY_DAYS_FOR_FORECAST` | Mindesthistorie für eine Vorhersage | `7` |

Ein anderes lokales Modell/anderer Server einsetzen: **nur** `AI_BASE_URL`
und `AI_MODEL` ändern, kein Code-Änderungsbedarf (Anforderung "lokal,
austauschbar").

## API

Vollständige, interaktive Dokumentation unter `/docs` (Swagger UI) bzw.
`/openapi.json`, sobald die Anwendung läuft.

| Endpunkt | Methode | Zweck |
|---|---|---|
| `/health` | GET | Status von DB und KI-Backend |
| `/stations` | GET | Liste der Tankstellen |
| `/prices/{station_uuid}` | GET | Preisverlauf (Parameter: `fuel_type`, `days`) |
| `/forecast/{station_uuid}` | GET | Vorhersage + Tankzeit-Empfehlung (Parameter: `fuel_type`, `horizon_hours`) |
| `/ask` | POST | Frage an die KI-Komponente (`station_uuid`, `fuel_type`, `question`, `use_context`) |

## Beispieldaten

`data/stations.csv` und `data/prices.csv` enthalten **synthetisch erzeugte**,
aber realistische Preisverläufe (Tagesmuster, Wochentagsmuster, langsamer
Trend, Rauschen, gelegentliche Preisschocks) für 3 Tankstellen über 120 Tage,
im Schema der öffentlichen
[Tankerkönig/MTS-K-Preishistorie](https://github.com/tankerkoenig/tankerkoenig-data).
Reproduzierbar erzeugt mit festem Zufalls-Seed via:

```bash
python -m scripts.generate_sample_data
```

**Warum synthetisch statt echte Daten?** Der Cloud-Entwicklungs-Workspace
hatte keinen Netzwerkzugriff auf GitHub-Rohdaten. Echte Daten lassen sich
jederzeit **ohne Code-Änderung** einsetzen: `stations.csv`/`prices.csv` im
selben Spaltenformat in `data/` ablegen (siehe Kommentar in
`scripts/generate_sample_data.py`).

## Tests

```bash
source .venv/bin/activate
pytest
```

Abgedeckt: Forecasting-Logik (u.a. Trend-Erkennung, Datenqualitätsprüfung,
Tankzeit-Fenster), Persistenz/Datenladen, KI-Client-Fehlerbehandlung (Erfolg,
4xx/5xx, Verbindungsfehler, Timeout, ungültiges Format - alle über
`httpx.MockTransport`, ohne echten Server), Groundedness-Validierung, sowie
End-to-End-API-Tests (mit einem austauschbaren Fake-KI-Client, siehe
`tests/test_api.py`).

## KI-Evaluation

Siehe [`evaluation/RESULTS.md`](evaluation/RESULTS.md) für Methodik, Metriken,
den Vergleich "mit vs. ohne gestützten Kontext" und die Analyse konkreter
Fehlerfälle. Ausführen:

```bash
python -m evaluation.run_evaluation
```

## KI-gestützte Entwicklung

Dieses Projekt wurde substanziell mit einem AI-Agent-Harness entwickelt
(Claude/Cowork, siehe `AI_DEVELOPMENT_LOG.md` für das vollständige
Entwicklungs-Log mit angenommenen/abgelehnten Vorschlägen und gefundenen
Fehlern). Der Agent lief in einem isolierten Cloud-Container ohne Zugriff auf
persönliche Dateien, Zugangsdaten oder andere Repositories, mit auf das
Projektverzeichnis beschränktem Datei-/Shell-Zugriff.

**Für die eigene Weiterarbeit mit einem Agent-Harness (z.B. Codex CLI,
OpenCode) auf dem eigenen Rechner:** in einem Dev-Container/einer VM/einem
OS-Sandbox mit auf dieses Projektverzeichnis beschränktem Dateizugriff
ausführen; Zugangsdaten nicht in Prompts/Code/Repository-Historie einbetten;
destruktive oder sicherheitsrelevante Befehle vor Ausführung bestätigen.

## Bekannte Grenzen / offene Punkte

- Dockerfile/docker-compose.yml sind syntaktisch geprüft, aber nicht in
  dieser Umgebung build-getestet (fehlender Registry-Zugriff, s.o.) - vor
  Abgabe einmal real ausführen.
- Die KI-Evaluation wurde bislang gegen einen regelbasierten Mock-Server
  durchgeführt (kein echtes Sprachmodell verfügbar) - vor Abgabe mit dem
  echten lokalen Modell wiederholen (`evaluation/RESULTS.md`).
- Die Vorhersage ist eine einfache, erklärbare statistische Schätzung
  (gleitender Durchschnitt + Saisonalität + linearer Trend), keine
  hochentwickelte Zeitreihenprognose - bewusste Design-Entscheidung zugunsten
  von Nachvollziehbarkeit und Testbarkeit.
- Konfidenzwerte sind heuristisch (Historienlänge + Streuung), keine
  kalibrierte Wahrscheinlichkeit - wird in API-Schema, System-Prompt und UI
  konsistent so kommuniziert.
- Beispieldaten sind synthetisch (siehe oben); echte Daten sind ohne
  Code-Änderung einsetzbar.
