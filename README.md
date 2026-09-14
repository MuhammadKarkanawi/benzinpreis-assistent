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
  ollama pull gemma3:4b
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

Das Compose-File bringt bewusst **keinen eigenen Ollama-Container** mehr mit
(frühere Version tat das) - es erwartet stattdessen einen bereits laufenden,
lokalen Ollama-Server auf dem Host. Das vermeidet doppelt vorgehaltene
Modelle/Container und Port-Konflikte, wenn auf demselben Rechner mehrere
Projekte dasselbe lokale Modell nutzen sollen (siehe
`AI_DEVELOPMENT_LOG.md`, Episode 5, Nachtrag 2):

```bash
cp .env.example .env

# einmalig: Ollama auf dem Host starten und Modell pullen (falls noch nicht vorhanden)
docker run -d --name ollama-shared -p 11434:11434 -v ollama:/root/.ollama ollama/ollama
docker exec ollama-shared ollama pull gemma3:4b

# Variante A: mit dem echten lokalen Modell (Defaults in docker-compose.yml
# passen bereits: http://host.docker.internal:11434/v1, gemma3:4b):
docker compose up --build

# Variante B: mit dem mitgelieferten Mock-KI-Server (kein Modell-Download nötig, nur Demo/Test):
AI_BASE_URL=http://mock-ai:8100/v1 AI_MODEL=mock-model \
  docker compose --profile mock up --build
```

`docker compose up app` (ohne Profil) startet den Dienst auch ganz allein -
degradiert (ohne KI-Antwortfunktion), aber lauffähig.

> ⚠️ **Wichtige Stolperfalle bei eigener lokaler `.env`:** Falls im
> Projektverzeichnis bereits eine `.env`-Datei für den *nativen* Lauf ohne
> Docker existiert (typischerweise mit `AI_BASE_URL=http://localhost:11434/v1`
> für den direkten Zugriff auf einen lokal installierten Ollama), lädt
> `docker compose` diese `.env` automatisch mit - und "localhost" bedeutet
> dann innerhalb des Containers den Container selbst, nicht den Host! Die
> KI-Komponente ist dann scheinbar grundlos "nicht erreichbar", obwohl der
> Container läuft, selbst wenn der Compose-Default eigentlich schon korrekt
> auf `host.docker.internal` zeigt (die `.env` überschreibt diesen Default).
> Deshalb im Zweifel `AI_BASE_URL`/`AI_MODEL` wie oben gezeigt explizit vor
> dem Befehl voranstellen - genau dieser Fall ist beim echten Build-Test
> aufgetreten, siehe `AI_DEVELOPMENT_LOG.md`, Episode 5 (Nachtrag).

> **Hinweis zur Entstehung:** Dieses Projekt wurde in einem Cloud-Entwicklungs-
> Workspace mit eingeschränktem Netzwerkzugriff entwickelt (kein Zugriff auf
> Docker Hub/Ollama/Hugging Face, siehe `AI_DEVELOPMENT_LOG.md`, Episode 5).
> Dockerfile/docker-compose.yml wurden auf einem echten Rechner **erfolgreich
> build- und funktionsgetestet** (App-Container + echter Ollama-Server, echte
> `/ask`-Anfrage gegen `gemma3:4b` erfolgreich gegründet beantwortet). Der
> anfängliche Aufbau mit einem projekteigenen, gebündelten Ollama-Container im
> Compose-File wurde danach bewusst zugunsten eines gemeinsam genutzten,
> host-seitigen Ollama-Servers verworfen (Nachtrag 2 in Episode 5) - das
> entspricht besser der Praxis, dieselbe lokale KI-Komponente über mehrere
> Projekte hinweg zu teilen.

## Konfiguration

Alle Werte sind über Umgebungsvariablen konfigurierbar (siehe `.env.example`
und `app/config.py`):

| Variable | Bedeutung | Beispiel |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy-Datenbank-URL | `sqlite:///./data/app.db` |
| `AI_BASE_URL` | Basis-URL des OpenAI-kompatiblen Inference-Servers | `http://localhost:11434/v1` |
| `AI_MODEL` | Modellname/-tag beim Inference-Server | `gemma3:4b` |
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
hatte keinen Netzwerkzugriff auf GitHub-Rohdaten, und ein historisches
Massen-Archiv echter Tankerkönig-Daten war zum Zeitpunkt der Entwicklung
nirgends aktuell/frei zugänglich (siehe AI_DEVELOPMENT_LOG.md, Episode 9).
Die synthetischen Preise liegen daher unterhalb des aktuellen realen
Preisniveaus (~1.6-1.8 statt ~2.2 EUR/Liter) - intern konsistent für
Forecasting/Grounding, aber nicht realitätsgetreu. Sie bleiben unverändert
als reproduzierbare Basis für Tests/Evaluation bestehen. Echte Daten lassen
sich zusätzlich **ohne Code-Änderung** einsetzen: entweder `stations.csv`/
`prices.csv` im selben Spaltenformat in `data/` ablegen (siehe Kommentar in
`scripts/generate_sample_data.py`), oder echte, wachsende Daten über die
unten beschriebenen Sammel-Skripte hinzufügen - letzteres ist inzwischen
produktiv im Einsatz (drei reale Stationen, siehe unten).

## Echte Daten sammeln (optional, vorbereitet)

Zusätzlich zu den synthetischen Beispieldaten gibt es zwei Skripte, um echte,
über die Zeit wachsende Preisdaten der öffentlichen Tankerkönig-API zu
sammeln - unabhängig von den synthetischen `data/*.csv` (die für
reproduzierbare Tests/Evaluation unverändert bleiben). Echte Stationen werden
dafür als zusätzliche Datenbank-Einträge angelegt.

**Voraussetzung:** ein kostenloser API-Key von
[onboarding.tankerkoenig.de](https://onboarding.tankerkoenig.de) (die
Registrierung war während der Entwicklung zunächst wegen Wartungsarbeiten
des Anbieters gesperrt, siehe `AI_DEVELOPMENT_LOG.md`, Episode 9). Inzwischen
liegt ein echter Key vor, und die beiden Skripte wurden erfolgreich gegen die
echte, laufende API verifiziert (reale Stationen gefunden, reale Preise auf
dem tatsächlichen Marktniveau gespeichert). Dabei gefunden und behoben: ein
zu knapper, jetzt über `TANKERKOENIG_TIMEOUT_SECONDS` konfigurierbarer
Timeout, sowie Stationen, die trotz unauffälligem Status keine Preise
liefern (z.B. vorübergehend geschlossen) - werden jetzt korrekt
übersprungen statt als Nur-Null-Datensatz gespeichert. Details:
`AI_DEVELOPMENT_LOG.md`, Episode 10.

```bash
# .env ergänzen: TANKERKOENIG_API_KEY=<dein-key>

# 1. Einmalig: echte Tankstellen in der Nähe suchen und auswählen
python -m scripts.discover_real_stations --lat 51.5136 --lng 7.4653 --radius 5
python -m scripts.discover_real_stations --lat 51.5136 --lng 7.4653 --radius 5 \
    --pick <uuid1>,<uuid2>,<uuid3> --write
# .env ergänzen: TANKERKOENIG_STATION_UUIDS=<uuid1>,<uuid2>,<uuid3>

# 2. Wiederkehrend (z.B. stündlich per cron/launchd): aktuelle Preise abrufen
python -m scripts.collect_real_prices
```

Ein Cron-Eintrag für stündliches Sammeln:

```
0 * * * *  cd /pfad/zum/projekt && .venv/bin/python -m scripts.collect_real_prices >> /pfad/zum/projekt/collect.log 2>&1
```


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

- Dockerfile/docker-compose.yml wurden real gebaut und gestartet (nicht nur
  syntaktisch geprüft) - siehe `AI_DEVELOPMENT_LOG.md`, Episode 5 (Nachtrag)
  und Episode 8.
- Die KI-Evaluation wurde final gegen das echte lokale Modell (`gemma3:4b`
  via Ollama) ausgeführt, nicht nur gegen den Mock - siehe
  `evaluation/RESULTS.md` und `AI_DEVELOPMENT_LOG.md`, Episode 7.
- Die Sammel-Skripte für echte Tankerkönig-Daten
  (`scripts/discover_real_stations.py`, `scripts/collect_real_prices.py`)
  sind inzwischen erfolgreich gegen die echte API verifiziert (siehe
  Abschnitt "Echte Daten sammeln" und `AI_DEVELOPMENT_LOG.md`, Episode 10) -
  drei reale Stationen sind angelegt, ein stündlicher Cron-Job sammelt
  laufend echte Preise.
- Die Vorhersage ist eine einfache, erklärbare statistische Schätzung
  (gleitender Durchschnitt + Saisonalität + linearer Trend), keine
  hochentwickelte Zeitreihenprognose - bewusste Design-Entscheidung zugunsten
  von Nachvollziehbarkeit und Testbarkeit.
- Konfidenzwerte sind heuristisch (Historienlänge + Streuung), keine
  kalibrierte Wahrscheinlichkeit - wird in API-Schema, System-Prompt und UI
  konsistent so kommuniziert.
- Beispieldaten sind synthetisch (siehe oben); echte Daten sind ohne
  Code-Änderung einsetzbar.
