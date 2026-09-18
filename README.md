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

## Problemstellung & Nutzerszenarien

**Problem:** Kraftstoffpreise schwanken mehrmals täglich nach erkennbaren
Mustern (Tageszeit, Wochentag, langsamer Trend) - wer "auf gut Glück" tankt,
zahlt im Schnitt mehr, als nötig wäre. Der Dienst macht diese Muster
sichtbar und übersetzt sie in eine konkrete, verständliche Empfehlung.

Vier repräsentative Nutzerszenarien:

1. **Tankzeit-Entscheidung:** Als Autofahrer will ich vor dem Wochenende
   wissen, ob ich heute noch oder besser morgen früh tanken sollte - der
   Dienst zeigt dafür Trend, Vorhersage und ein konkretes Zeitfenster
   ("beste Tankzeit") für die nächsten 48 Stunden.
2. **Preisverlauf verstehen:** Als Nutzer will ich den Preisverlauf der
   letzten 14 Tage einer Tankstelle auf einen Blick sehen, um zu
   beurteilen, ob der aktuelle Preis im Vergleich zum bisherigen Muster
   gerade günstig oder teuer ist.
3. **Frage in natürlicher Sprache:** Als Nutzer will ich nicht selbst Zahlen
   interpretieren müssen, sondern in eigenen Worten fragen ("wird der Preis
   heute noch fallen?", "was ist günstiger, E10 oder Diesel?") und eine
   Antwort erhalten, die sich strikt auf die tatsächlich berechneten Fakten
   stützt statt auf erfundene Zahlen.
4. **Vertrauen in die Vorhersage einschätzen:** Als Nutzer will ich wissen,
   wie sicher eine Vorhersage ist, bevor ich mich darauf verlasse - der
   Dienst liefert dafür einen erklärten, ausdrücklich nicht als kalibrierte
   Wahrscheinlichkeit missverständlichen Konfidenzwert, und die KI-Komponente
   relativiert überzogene Sicherheitsfragen entsprechend.

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

## Verantwortungsvolles Design (Responsible Design)

**Datenschutz:** Es findet kein Login und keine Erfassung personenbezogener
Daten statt (Anforderung "single local user"). Gespeichert werden
ausschließlich Tankstellen-Stammdaten (öffentlich, Tankerkönig-Schema),
Preisdaten sowie `QueryLog`-Einträge (gestellte Frage, Antwort,
Groundedness-Flag) zur Nachvollziehbarkeit der KI-Komponente - keine
Nutzer-Identifikatoren, IP-Adressen o.ä. werden persistiert.

**Sicherheit:** Der `TANKERKOENIG_API_KEY` liegt ausschließlich in der
lokalen, nicht versionierten `.env` (siehe `.gitignore`), nie im Code oder
in der Git-Historie. Der KI-Agent-Harness lief in einem auf das
Projektverzeichnis beschränkten, isolierten Cloud-Container ohne Zugriff auf
persönliche Dateien, Zugangsdaten oder andere Repositories (Details siehe
Abschnitt "KI-gestützte Entwicklung" oben). Die Anwendung selbst geht von
einem einzelnen lokalen Nutzer ohne Mehrbenutzer-/Rechteverwaltung aus
(Scope-Regel der Aufgabenstellung).

**Potenzieller Missbrauch:** `/ask` ist bewusst kein allgemeiner Chatbot,
sondern strikt an die Kraftstoffpreis-Fakten der jeweiligen Tankstelle
gebunden (System-Prompt + `app/ai/validation.py`). Themenfremde Fragen
(z.B. Finanz-/Anlageberatung) werden erkennbar abgelehnt statt beantwortet -
in der Evaluation eigens als Kategorie `out_of_scope` getestet
(Ablehnungsquote 1.00, siehe `evaluation/RESULTS.md`). Eine böswillige
Umleitung der KI-Komponente zu fachfremden Zwecken ist damit erheblich
erschwert, aber wie bei jedem LLM-Prompt nicht vollständig ausgeschlossen.

**Kennzeichnung KI-generierter Ergebnisse:** Preis, Vorhersage und
Tankzeit-Empfehlung stammen ausschließlich aus der deterministischen
Kernlogik (`app/forecasting.py`) - nur die Freitext-*Erklärung* dazu kommt
vom lokalen Sprachmodell. UI und API halten das strikt getrennt: Zahlen
erscheinen in eigenen, klar benannten Feldern/Kacheln (`current_price`,
`predicted_price`, ...), die KI-Antwort erscheint separat im Antwortfeld von
`/ask` mit einem sichtbaren Warn-Hinweis (`flagged_ungrounded`), falls die
automatische Prüfung unbelegte Zahlen entdeckt.

## Bekannte Grenzen / offene Punkte

- ~~Dockerfile/docker-compose.yml nicht build-getestet~~ - erledigt: auf
  einem echten Rechner erfolgreich build- und funktionsgetestet (App-Container
  + echter Ollama-Server, siehe oben und `AI_DEVELOPMENT_LOG.md`, Episode 5).
- ~~KI-Evaluation nur gegen Mock-Server~~ - erledigt: finaler Lauf gegen das
  echte lokale Modell (`gemma3:4b`) durchgeführt, drei dabei aufgedeckte reale
  Probleme behoben und verifiziert (siehe `evaluation/RESULTS.md`,
  `AI_DEVELOPMENT_LOG.md` Episode 7).
- Die Vorhersage ist eine einfache, erklärbare statistische Schätzung
  (gleitender Durchschnitt + Saisonalität + linearer Trend), keine
  hochentwickelte Zeitreihenprognose - bewusste Design-Entscheidung zugunsten
  von Nachvollziehbarkeit und Testbarkeit.
- Konfidenzwerte sind heuristisch (Historienlänge + Streuung), keine
  kalibrierte Wahrscheinlichkeit - wird in API-Schema, System-Prompt und UI
  konsistent so kommuniziert.
- Die mitgelieferten Beispieldaten (`data/stations.csv`/`prices.csv`) sind
  synthetisch (siehe oben); im laufenden Betrieb sammelt die Anwendung
  inzwischen zusätzlich echte Preisdaten für 22 reale Tankstellen im Raum
  Dortmund über die Tankerkönig-API (`scripts/discover_real_stations.py`,
  `scripts/collect_real_prices.py`), live verifiziert (siehe
  `AI_DEVELOPMENT_LOG.md`, Episode 10).
