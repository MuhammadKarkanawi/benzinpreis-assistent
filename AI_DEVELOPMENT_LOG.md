# AI-Development-Log

Agent-Harness: Claude (Cowork), betrieben in einem isolierten Cloud-Container
(kein Zugriff auf persönliche Dateien außerhalb des Projektverzeichnisses,
kein Root-Zugriff auf das Host-System, eingeschränkter Netzwerkzugriff über
eine organisationsweite Egress-Allowlist - siehe Episode 6). Zugriff:
Datei-Tools (Lesen/Schreiben/Editieren) und eine Shell, beschränkt auf das
Projektverzeichnis und das Cloud-Arbeitsverzeichnis. Es gab keinen Zugriff auf
Zugangsdaten, private SSH-Keys oder andere Repositories.

Die folgenden Episoden sind eine repräsentative Auswahl aus der tatsächlichen
Entwicklungssitzung, keine vollständige Mitschrift.

---

## Episode 1: Projekt-Grundgerüst (Config, Modelle, Datenbank)

- **Auftrag:** FastAPI-Projektstruktur anlegen: Konfiguration (env-basiert),
  SQLModel-Datenmodelle (Station, PriceRecord, ForecastResult, QueryLog),
  DB-Session-Handling.
- **Vorschlag des Agenten:** Vollständige Dateien für `app/config.py`,
  `app/models.py`, `app/db.py`, `app/schemas.py` in einem Zug.
- **Rechte/Tools:** Datei-Schreibzugriff im Projektverzeichnis.
- **Verifikation:** Noch keine Laufzeitprüfung an dieser Stelle (folgt in
  Episode 2/3), nur Konsistenzprüfung der Feldnamen zwischen Modellen/Schemas.
- **Ergebnis:** Unverändert übernommen.
- **Beobachtung:** Reine Struktur-Generierung ohne Ausführung ist die
  riskanteste Phase - Tippfehler in Feldnamen fallen erst beim ersten
  Testlauf auf. Deshalb wurde direkt danach ein lauffähiger Smoke-Test
  gemacht (Episode 2).

## Episode 2: Nicht-KI-Kernlogik (Zeitreihen-Forecast) - Fehler gefunden und korrigiert

- **Auftrag:** Deterministische Vorhersagelogik (gleitende Durchschnitte,
  Wochentags-/Tageszeit-Saisonalität, linearer Trend, Tankzeit-Empfehlung,
  heuristische Konfidenz).
- **Vorschlag des Agenten:** Erste Implementierung berechnete die saisonale
  Abweichung je (Wochentag, Stunde) gegen den GESAMT-Mittelwert der Historie.
- **Verifikation:** Automatisierter Test mit synthetischen Daten mit klar
  steigendem/fallendem Trend (`tests/test_forecasting.py`). **Test schlug
  fehl:** Bei einem eindeutig steigenden Trend sagte die Funktion "fallend"
  voraus (Vorzeichenumkehr).
- **Ursachenanalyse:** Ein starker langfristiger Preistrend "leckte" in die
  vermeintlich saisonale Komponente, weil bei kurzer Historie nicht jeder
  Wochentag gleich oft an frühen/späten Tagen des Datensatzes vorkommt.
- **Ergebnis:** VERWORFEN und neu implementiert: saisonale Abweichung wird
  jetzt gegen einen gleitenden 7-Tage-Mittelwert je Zeitpunkt gebildet
  (entfernt Trend, behält Wochentags-/Tagesmuster). Zusätzlich wurde die
  Stabilitätsschwelle (0.01 € auf 0.005 €) neu kalibriert, da sie sich sonst
  zufällig genau mit der Trendgröße im Test überschnitt. Nach dem Fix: alle
  Tests grün.
- **Beobachtung/Risiko:** Ein rein statistisches Modul kann einen subtilen,
  aber folgenreichen methodischen Fehler enthalten (falsches Vorzeichen einer
  Vorhersage!), der ohne einen gezielten Test mit bekanntem Erwartungswert
  unentdeckt geblieben wäre. Reine Codeinspektion hätte das nicht
  zuverlässig aufgedeckt.

## Episode 3: Lokale KI-Komponente (Client, Prompting, Grounding-Validierung)

- **Auftrag:** OpenAI-kompatiblen Client für einen lokalen Inference-Server,
  strikt gegründete Prompt-Konstruktion, automatisierte Prüfung auf erfundene
  Zahlen ("Groundedness").
- **Vorschlag des Agenten:** `httpx`-basierter Client mit expliziten
  Fehlerklassen (nicht erreichbar/Timeout/ungültige Antwort), regexbasierte
  Zahlen-Extraktion zur Groundedness-Prüfung.
- **Rechte/Tools:** Datei-Schreibzugriff; später `pytest` mit
  `httpx.MockTransport` (kein echter Netzwerkzugriff nötig/genutzt).
- **Verifikation:** 6 automatisierte Tests je Fehlerklasse (Erfolg, 4xx, 5xx,
  Connect-Error, Timeout, ungültiges Antwortformat) - alle grün.
- **Ergebnis:** Angenommen. Kleinere Anpassung: `AIClient` erhielt einen
  optionalen `transport`-Parameter, damit Tests ohne echten Server laufen
  können, ohne Produktionscode-Pfade zu verändern.

## Episode 4: Dashboard-UI - visuelle Verifikation aufgedeckte einen CSS-Fehler

- **Auftrag:** Eigenständige Weboberfläche (Preisverlauf-Chart, Vorhersage,
  Tankzeit-Empfehlung, Frage-Eingabe) ohne externe CDN-Abhängigkeiten.
- **Vorschlag des Agenten:** Einzelne `index.html` mit eingebettetem
  Vanilla-JS/CSS, eigener Canvas-Chart (keine externe Chart-Bibliothek).
- **Verifikation:** Anwendung + Mock-KI-Server lokal gestartet, Seite per
  Playwright (Headless-Chromium) geöffnet, Screenshot geprüft UND
  Konsolen-Fehler ausgelesen.
- **Ergebnis:** TEILWEISE korrigiert - der Screenshot zeigte einen
  überlaufenden/verklebten Text bei der Methodenanzeige
  ("Methodeweighted_moving_average..."), da der Methodenname keine
  Leerzeichen enthielt. Behoben durch Anzeige-Formatierung (Ersetzen von
  `_`/`+` durch Leerzeichen) statt Änderung der internen Methodenbezeichnung.
  Zusätzlich ein harmloser 404-Konsolenfehler (fehlendes Favicon) durch
  einen leeren Data-URI-Favicon behoben.
- **Beobachtung:** Ohne den Screenshot wäre dieser rein visuelle Fehler nicht
  aufgefallen - die API-Daten waren korrekt, nur die Darstellung fehlerhaft.

## Episode 5: Containerisierung - Umgebungseinschränkung erkannt und dokumentiert

- **Auftrag:** Dockerfile + docker-compose.yml für unabhängige,
  containerisierte Ausführung inkl. lokalem KI-Backend.
- **Verifikation (Versuch):** `docker pull` / `docker compose config` im
  Cloud-Entwicklungs-Workspace ausprobiert.
- **Ergebnis:** Der Workspace hat keinen Netzwerkzugriff auf Docker Hub,
  GitHub-Rohdaten oder Ollama/Hugging Face (organisationsweite
  Egress-Beschränkung des Cloud-Containers - explizit NICHT umgangen, siehe
  Richtlinie "do not retry organization policy denials"). `docker compose
  config` (reine Syntaxprüfung ohne Netzwerk) wurde erfolgreich verifiziert,
  ein echter `docker build`/`up` konnte in dieser Umgebung nicht getestet
  werden.
- **Konsequenz/Risiko:** Dockerfile und docker-compose.yml waren zu diesem
  Zeitpunkt syntaktisch/strukturell geprüft, aber NICHT build-getestet.
- **Nachtrag (nach Übertragung auf den echten Rechner):** `docker compose
  --profile real up --build` wurde real ausgeführt und **erfolgreich
  verifiziert** - App-Image baut, App- und Ollama-Container starten,
  `/health` meldet `ai_backend_reachable: true`, und eine echte `/ask`-Anfrage
  gegen `gemma3:4b` liefert eine korrekt gegründete Antwort
  (`flagged_ungrounded: false`) mit allen erwarteten Fakten (Preis, Vorhersage,
  Tankzeit-Empfehlung, Kraftstoffvergleich).
  Dabei ein weiterer, realer Fehler gefunden und behoben: Die lokale
  `.env`-Datei enthält `AI_BASE_URL=http://localhost:11434/v1` (richtig für
  den *nativen* Lauf ohne Docker). `docker compose` lädt diese `.env` jedoch
  automatisch, und "localhost" bedeutet innerhalb des `app`-Containers den
  Container selbst statt den Host - der erste Startversuch scheiterte
  dadurch mit "Inference-Server nicht erreichbar", obwohl beide Container
  liefen. Fix: keine Code-Änderung nötig, sondern `AI_BASE_URL`/`AI_MODEL`
  beim Aufruf explizit voranstellen (überschreibt die `.env`-Werte), wie im
  Kommentarkopf von `docker-compose.yml` bereits dokumentiert - zusätzlich
  in der README als expliziter Warnhinweis ergänzt, da genau dieser Fall in
  der Praxis aufgetreten ist.
- **Nachtrag 2 (bewusste Design-Änderung, nach Rücksprache mit dem
  Studierenden):** Der Studierende nutzt dasselbe lokale Modell (`gemma3:4b`
  über Ollama) parallel auch für zwei weitere, eigene Projekte auf demselben
  Rechner (`receipt-intelligence`, `Flashcard Learning Assistant`) und hat
  dafür einen einzelnen, projektübergreifend laufenden Ollama-Container
  (`ollama-shared`) eingerichtet, statt in jedem Projekt einen eigenen
  Ollama-Container/eigenes Modell vorzuhalten. Der ursprünglich in
  `docker-compose.yml` gebündelte, projekteigene `ollama`-Service (Profil
  "real") wäre dazu inkonsistent gewesen und hätte bei gleichzeitigem Betrieb
  denselben Port-11434-Konflikt verursacht, der zuvor bereits bei
  `receipt-intelligence` auftrat (siehe dortige Migration). **Vorschlag des
  Agenten:** den `ollama`-Service und das zugehörige Volume aus
  `docker-compose.yml` entfernen, den `app`-Dienst stattdessen standardmäßig
  auf `http://host.docker.internal:11434/v1` (Modell `gemma3:4b`) zeigen zu
  lassen - identisches Muster wie in den beiden anderen Projekten. **Ergebnis:**
  angenommen. `docker compose config` (Syntaxprüfung) für Standard- und
  `mock`-Profil erneut erfolgreich verifiziert; ein erneuter echter
  `docker compose up --build` gegen den bestehenden `ollama-shared`-Container
  steht noch aus (siehe README, Abschnitt "Mit Docker Compose").
  **Kompromiss/Risiko:** Für sich allein genommen ist das Projekt dadurch
  nicht mehr *vollständig* eigenständig containerisiert - ein Prüfer ohne
  bereits laufenden lokalen Ollama-Server muss vor `docker compose up` einmal
  manuell einen solchen starten und das Modell pullen (zwei zusätzliche
  Befehle, in der README dokumentiert), statt dass ein einziger
  `docker compose --profile real up --build` alles allein bereitstellt. Diese
  Änderung wurde bewusst und nach expliziter Anweisung des Studierenden
  vorgenommen, der diesen Kompromiss für seinen Anwendungsfall (ein
  gemeinsames lokales Modell für mehrere eigene Projekte) akzeptiert hat.

## Episode 6: KI-Evaluation - zwei echte Schwachstellen der Grounding-Logik gefunden

- **Auftrag:** Evaluationsfälle definieren und automatisiert gegen die
  KI-Komponente ausführen (grounded vs. ungrounded Baseline).
- **Verifikation:** 13 Fälle x 2 Modi über `evaluation/run_evaluation.py`
  ausgeführt, Antworten manuell durchgesehen.
- **Ergebnis - zwei akzeptierte Korrekturen:**
  1. Fall "Ist E10 günstiger als Diesel?": Die Fakten enthielten nur die
     ausgewählte Kraftstoffsorte, die Antwort ignorierte die eigentliche
     Frage. Fix: `other_current_prices_eur` zu den Fakten hinzugefügt
     (app/ai/grounding.py) plus Prompt-Regel, dass sich Vorhersage/Tankzeit
     nicht auf andere Sorten übertragen lässt.
  2. Fall "Preis in 5 Jahren?": Es wurde trotzdem eine 24h-Vorhersagezahl
     genannt. Fix: explizite Prompt-Regel für Anfragen weit außerhalb von
     `forecast.horizon_hours`.
- **Beobachtung/Risiko (nicht behoben, bewusst offen dokumentiert):** Der
  mitgelieferte Mock-Server ist regelbasiert und daher kein verlässlicher
  Nachweis, dass ein ECHTES Sprachmodell dieselben Prompt-Regeln befolgt
  (Regel-Befolgung ist bei LLMs nicht garantiert). Siehe
  `evaluation/RESULTS.md`, Abschnitt "Einschränkung": Der komplette
  Evaluationslauf muss vor der Abgabe mit einem echten lokalen Modell
  wiederholt werden - dafür ist keine Code-Änderung nötig, nur
  `AI_BASE_URL`/`AI_MODEL`.

## Episode 7: Evaluation mit dem echten lokalen Modell (gemma3:4b) - drei reale, mock-blinde Probleme gefunden und behoben

- **Kontext:** Nach Abschluss der Entwicklung im Cloud-Workspace (ohne
  Netzwerkzugriff auf einen echten Inference-Server, siehe Episode 5) wurde
  das Projekt auf den eigenen Rechner des Studierenden übertragen und dort
  zum ersten Mal gegen ein echtes, lokal über Ollama laufendes Modell
  (`gemma3:4b`) getestet - inklusive eines vollständigen Evaluationslaufs
  (`evaluation/run_evaluation.py`, 13 Fälle x 2 Modi).
- **Erster echter Lauf (vor jeder Korrektur) deckte drei Probleme auf**, die
  der bis dahin verwendete regelbasierte Mock (Episode 5/6) nicht zeigen
  konnte, weil er weder echte Ladezeiten noch echtes, freies
  Sprachmodell-Verhalten hat:
  1. **Kaltstart-Timeouts:** 4 von 13 grounded-Anfragen schlugen mit
     "Zeitüberschreitung beim Aufruf des Inference-Servers" fehl (~60s,
     Timeout + 1 Retry), obwohl ab dem 5. Fall jede Antwort zuverlässig in
     5-9s kam. Ursachenanalyse: Ollama musste `gemma3:4b` beim allerersten
     Aufruf erst vollständig in den Arbeitsspeicher laden: reiner
     Kaltstart-Effekt, keine Fehlfunktion der Anwendung.
  2. **Falscher "ungegründet"-Alarm bei Prozentangaben:** Das Modell gab den
     heuristischen Konfidenzwert korrekt als Prozentzahl aus ("geschätzt
     78,1%" statt "0,781") - eine legitime, korrekte Umrechnung. Die
     `is_grounded()`-Prüfung (`app/ai/validation.py`) kannte aber nur die
     rohe Dezimalform aus den Fakten und wertete "78,1" fälschlich als
     erfundene Zahl (Groundedness-Rate im ersten echten Lauf: nur 0.846
     statt der erwarteten ~1.0).
  3. **Zu enge Heuristiken im Evaluationsskript selbst** (nicht in der
     Anwendung!): Bei der Frage "Welche Aktie sollte ich kaufen?" lehnte das
     Modell korrekt mit "Ich kann Ihnen leider keine Anlageberatung geben"
     ab - die Ablehnungs-Stichwortliste in `evaluation/run_evaluation.py`
     kannte aber nur "Finanzberatung", nicht das Synonym "Anlageberatung",
     und zählte den (tatsächlich korrekt abgelehnten) Fall als "nicht
     abgelehnt" (Ablehnungsquote: 0.667 statt 1.0). Ebenso stufte die
     Überconfidence-Prüfung jedes Vorkommen von "100%" als überheblich ein,
     auch wenn die Antwort die Aussage gerade explizit verneinte ("... ist
     die Vorhersage nicht zu 100% garantiert") - Überconfidence-Rate: 1.00
     statt der inhaltlich korrekten 0.00.
- **Vorschlag des Agenten:** (a) ein einmaliger, nicht in die Metriken
  eingerechneter Warm-up-Aufruf vor dem eigentlichen Evaluationslauf UND
  beim Start der Anwendung selbst (`app/main.py`, als nicht blockierender
  Hintergrund-Task), damit auch ein echter Nutzer nicht den ersten,
  potenziell langsamen Aufruf zu spüren bekommt; (b) `is_grounded()`
  erweitert, sodass Zahlen zwischen 0 und 1 aus den Fakten zusätzlich in
  ihrer Prozent-Schreibweise (x100) als gültig gelten; (c) die
  Ablehnungs-Stichwortliste um "Anlageberatung" ergänzt und die
  Überconfidence-Prüfung verneinungssensitiv gemacht (prüft die 30 Zeichen
  vor einem Marker auf "kein/keine/nicht/...").
- **Verifikation:** Zwei neue Regressionstests für den Prozent-Fall in
  `tests/test_validation.py` (alle 32 Tests weiterhin grün, auf dem echten
  Rechner UND im Cloud-Workspace). Anschließend der komplette
  Evaluationslauf erneut gegen das echte Modell ausgeführt.
- **Ergebnis - Fixes bestätigt wirksam:**

  | Metrik | vor den Fixes | nach den Fixes |
  |---|---|---|
  | Fehlerrate grounded | 0.308 | 0.00 |
  | Groundedness-Rate grounded | 0.846 | 1.00 |
  | Ablehnungsquote out_of_scope | 0.667 | 1.00 |
  | Überconfidence-Rate (uncertainty) | 1.00 | 0.00 |

  Details siehe `evaluation/RESULTS.md`.
- **Beobachtung/Risiko:** Dies ist der deutlichste Beleg im gesamten Projekt
  dafür, dass ein regelbasierter Mock die Evaluation einer echten
  KI-Komponente nicht ersetzen kann - nicht, weil das echte Modell schlechter
  performt hätte (inhaltlich hat es sich in allen drei Fällen korrekt
  verhalten!), sondern weil unsere eigene Test-/Infrastruktur-Annahmen
  (Timeout-Bemessung, erwartetes Zahlenformat, erwartete Formulierungen)
  falsch kalibriert waren. Eine Evaluation, die nur gegen den Mock gelaufen
  wäre, hätte alle drei Probleme unentdeckt gelassen und ein zu optimistisches
  Bild gezeichnet - bzw. hier sogar ein zu pessimistisches, da das Modell in
  Wahrheit besser funktionierte, als die (fehlerhafte) Messung zunächst zeigte.

## Episode 8: Nativer Lauf ohne Docker - Python-3.14-Inkompatibilitaet und ein irrefuehrender Netzwerk-"Bug", der in Wahrheit ein Port-Konflikt war

- **Kontext:** Der Studierende nutzt denselben Rechner parallel fuer zwei
  weitere eigene Projekte (`receipt-intelligence`, `flashcard-learning-assistant`),
  die ebenfalls den gemeinsamen `ollama-shared`-Container nutzen (siehe
  Episode 5, Nachtrag 2). Um Port-Kollisionen zwischen allen dreien zu
  vermeiden, wurden feste, unterschiedliche Ports vergeben
  (`receipt-intelligence`=8000, `flashcard-learning-assistant`=8001,
  `benzinpreis-assistent`=8002) und zusaetzlich ein nativer Lauf (ohne
  Docker) von `benzinpreis-assistent` gegen das echte Modell verifiziert.

- **Problem 1 - echte Umgebungs-Inkompatibilitaet:** Die lokale `.venv` war
  zwischenzeitlich (vermutlich durch ein Homebrew-Update) von Python 3.12 auf
  3.14 "gerutscht" (eine `venv` verweist nur per Symlink auf den
  System-Interpreter, kopiert ihn nicht). Der native Start scheiterte mit
  `pydantic.errors.PydanticUserError: Field 'id' requires a type annotation`
  beim Erzeugen des `Station`-Modells. **Ursachenanalyse:** Python 3.14 fuehrt
  standardmaessig verzoegert ausgewertete Annotationen ein (PEP 649), womit
  die gepinnte `pydantic`/`SQLModel`-Version (Stand 2024/2025) noch nicht
  zurechtkam - kein Fehler in unserem Code. **Fix:** `.venv` explizit mit
  `python3.12 -m venv .venv` neu angelegt; alle 32 Tests liefen danach wieder
  fehlerfrei.

- **Problem 2 - der eigentlich lehrreiche Teil:** Nach dem venv-Fix meldete
  `/health` weiterhin `ai_backend_reachable: false`, obwohl `curl` direkt
  gegen `http://127.0.0.1:11434/v1/models` zuverlaessig `200` lieferte. Der
  Agent verfolgte zwei Hypothesen, bevor die wahre Ursache gefunden wurde:
  1. *Verworfene Hypothese A (IPv6/IPv4-Aufloesung von "localhost"):*
     naheliegend, da genau dieses Muster bei einem frueheren, aehnlichen Fall
     tatsaechlich die Ursache war. Bereits vorsorglich auf `127.0.0.1` in der
     `.env` umgestellt - behob das Problem hier aber nicht.
  2. *Verworfene Hypothese B (uvloop-Bug):* `uvicorn` nutzt standardmaessig
     `uvloop` statt der Standard-`asyncio`-Loop. Verifikation durch zwei
     isolierte Kontrollskripte (derselbe `httpx`-Aufruf einmal mit
     Standard-`asyncio`, einmal mit `uvloop.install()`) - **beide liefen
     fehlerfrei**, was diese Hypothese widerlegte, statt sie einfach
     anzunehmen.
  3. *Tatsaechliche Ursache:* Ein temporaerer Debug-Umbau von `app/routers/health.py`
     (zunaechst `print()`, dann - da nicht einmal das erschien - ein
     Datei-Log nach `/tmp/`) zeigte: der Code-Pfad wurde ueberhaupt nicht
     ausgefuehrt. `lsof -nP -iTCP:8002 -sTCP:LISTEN` deckte auf, dass **zwei**
     Prozesse denselben Port belegten: ein alter, noch laufender
     Docker-Container `benzinpreis-assistent-app-1` (gebunden an `*:8002`,
     also alle Interfaces) UND der neue native `uvicorn`-Prozess (gebunden an
     `127.0.0.1:8002`). macOS erlaubte beide Bindungen gleichzeitig,
     Anfragen an `localhost:8002` wurden dadurch inkonsistent bedient -
     vermutlich ueberwiegend vom alten Container mit seinem laengst
     ueberholten, eingebauten Code, nicht vom live editierten nativen
     Prozess. **Deshalb zeigte jede unserer Code-Aenderungen scheinbar keine
     Wirkung** - das eigentliche Raetsel war also kein Anwendungsfehler,
     sondern ein reiner Infrastruktur-Konflikt, der aus den
     Anwendungs-Logs allein nicht erkennbar war.
  - **Fix:** `docker stop benzinpreis-assistent-app-1` waehrend des nativen
    Tests; danach lieferte `/health` sofort `ai_backend_reachable: true`.
    Dauerhaft: jedes der drei Projekte bekam einen festen, exklusiven
    Host-Port (siehe oben), sodass native und containerisierte Laeufe
    kuenftig nicht mehr um denselben Port konkurrieren koennen.

- **Verifikation:** Nach dem Fix lieferte `/health` durchgehend
  `ai_backend_reachable: true`; eine echte `/ask`-Anfrage gegen `gemma3:4b`
  (nativ, Port 8002) ergab eine korrekt gegruendete, kohaerente Antwort mit
  den tatsaechlichen Fakten (Preis, Methode, Konfidenz). Alle 32 Tests
  blieben gruen.

- **Beobachtung/Risiko:** Die wertvollste Lektion dieser Episode ist nicht
  der Python-3.14-Fund (ein klarer, schnell behobener Kompatibilitaetsfehler),
  sondern der zweite Fall: ein scheinbarer Anwendungs-/Netzwerk-Bug, der sich
  bei genauerem Hinsehen als reiner Infrastruktur-Konflikt (doppelt belegter
  Port) entpuppte. Der Agent ging dabei methodisch vor - stellte eine
  plausible Hypothese (uvloop) auf, **testete sie gezielt und verwarf sie
  anhand des Testergebnisses**, statt sie unbelegt als Erklaerung stehen zu
  lassen - und griff erst danach auf eine grundlegendere Betriebssystem-Ebene
  (`lsof`) zurueck, um die tatsaechliche Ursache zu finden. Ohne dieses
  schrittweise Ausschlussverfahren waere vermutlich fälschlich am
  Anwendungscode weitergesucht oder -geaendert worden, obwohl dieser die
  ganze Zeit korrekt war.

## Episode 9: Docker-Endverifikation deckte einen zweiten `.env`-Bug auf; reale vs. synthetische Preise - Sammel-Infrastruktur fuer echte Tankerkoenig-Daten vorbereitet

- **Kontext:** Nach Episode 8 (feste Ports, native Verifikation) folgte
  planmaessig die abschliessende Docker-Verifikation mit dem neuen
  Port-Schema (8000/8001/8002) und dem geteilten `ollama-shared`-Container.

- **Problem 1 (Docker-Endverifikation):** `docker compose up -d --build app`
  baute erfolgreich, aber `/ask` scheiterte mit "Inference-Server nicht
  erreichbar unter http://127.0.0.1:11434/v1/chat/completions". **Ursachenanalyse:**
  `docker compose` liest projektweit automatisch die `.env`-Datei ein, um
  `${VAR:-default}`-Platzhalter in `docker-compose.yml` aufzuloesen - unabhaengig
  von einem etwaigen `env_file:`-Eintrag. Die lokale `.env` war (korrekt fuer den
  nativen Lauf aus Episode 8) auf `127.0.0.1` gesetzt; dieser Wert
  ueberschrieb beim Container-Start also den eigentlich fuer den Container
  vorgesehenen Default `host.docker.internal`. **Fix:** `AI_BASE_URL` im
  `environment:`-Block von `docker-compose.yml` fest codiert (kein
  `${...}`-Platzhalter mehr fuer diese eine Variable) - dauerhaft behoben,
  kein manuelles Voranstellen beim Start mehr noetig. Nach dem Fix: `/health`
  meldet `ai_backend_reachable: true` mit
  `ai_base_url: http://host.docker.internal:11434/v1`, und eine echte
  `/ask`-Anfrage liefert eine korrekt gegruendete Antwort.

- **Problem 2 (fachlicher Hinweis des Studierenden):** Bei der Kontrolle fiel
  auf, dass die synthetischen Beispieldaten Preise um ~1,6-1,8 EUR/Liter
  zeigen, waehrend reale Preise aktuell bei ~2,2 EUR/Liter liegen - ein
  Realitaetsbruch, der bei einer Abgabe unangenehm auffallen koennte.
  - *Recherche:* offizielle Tankerkoenig-Registrierung
    (onboarding.tankerkoenig.de) aktuell wegen Wartungsarbeiten gesperrt;
    kein aktuell erreichbares historisches Bulk-Archiv gefunden (mehrere
    GitHub-Forks stichprobenartig geprueft, alle veraltet/leer aus
    2019-2021; das offizielle historische Archiv liegt auf Azure DevOps,
    von der Organisations-Firewall des Agenten blockiert).
  - *Vorschlag des Agenten (nach Ruecksprache mit dem Studierenden):* da
    echte historische Daten nicht beschaffbar sind, stattdessen eine
    Sammel-Infrastruktur fuer zukuenftige echte Daten bauen (mit
    Platzhalter-Konfiguration), zur spaeteren Aktivierung sobald die
    Registrierung wieder moeglich ist.
  - *Ergebnis:* angenommen. Neu: `app/integrations/tankerkoenig_client.py`
    (`TankerkoenigClient`, gleiches injizierbares-Transport-Muster wie
    `AIClient`), `scripts/discover_real_stations.py` (einmalige, interaktive
    Stationssuche), `scripts/collect_real_prices.py` (wiederkehrender,
    fuer Scheduler (cron/launchd) gedachter Sammel-Job, der sich ohne
    gesetzten API-Key/Stationen fehlerfrei selbst deaktiviert), sowie die
    Konfigurationsfelder `tankerkoenig_api_key`/`tankerkoenig_station_uuids`.
  - *Wichtige Einschraenkung, offen dokumentiert:* Das exakte JSON-Antwortschema
    der Tankerkoenig-API (Feldnamen etc.) konnte mangels erreichbarem Key
    NICHT gegen die echte, laufende API verifiziert werden - der Client
    basiert auf der oeffentlich dokumentierten Schnittstellenbeschreibung,
    bleibt aber bis zur ersten echten Nutzung ungetestet gegen Live-Daten
    (siehe README, Abschnitt "Echte Daten sammeln").

- **Verifikation:** 12 neue Tests (7 fuer `TankerkoenigClient` ueber
  `httpx.MockTransport`, 5 fuer `collect_real_prices.py` ueber `monkeypatch`,
  beide ohne echten Netzwerkzugriff) - alle gruen, sowohl im
  Cloud-Entwicklungs-Workspace als auch (vom Studierenden selbst im echten
  Terminal ausgefuehrt, da die Remote-Geraete-Bruecke keine native
  macOS-`.venv`-Binaerdateien ausfuehren kann) auf seinem eigenen Rechner:
  44 von 44 Tests insgesamt.

- **Beobachtung/Risiko:** Zwei unabhaengige, aber aehnlich gelagerte
  `.env`-Ueberschreibungen (Episode 5 Nachtrag 1: manuelles Voranstellen von
  `AI_BASE_URL`; hier: automatisches Einlesen der `.env` durch
  `docker compose` selbst) zeigen ein wiederkehrendes Muster: Variablen, die
  fuer den einen Ausfuehrungsmodus (nativ) korrekt sind, koennen in einem
  anderen Modus (containerisiert) unbeabsichtigt wirksam werden, wenn
  dieselbe `.env`-Datei fuer beide genutzt wird. Fuer produktionsnahe
  Deployments waere eine strikte Trennung (z.B. `.env.native` vs.
  `.env.docker`) robuster als die hier gewaehlte punktuelle Fest-Codierung
  einer einzelnen Variable. Ausserdem bleibt die reale Tankerkoenig-Anbindung
  bewusst ein unverifizierter, aber sauber getesteter und dokumentierter
  Kompromiss, der auf eine ausserhalb der eigenen Kontrolle liegende
  externe Bedingung (Wiederoeffnung der Registrierung) wartet.

---

## Zusammenfassung: akzeptiert / modifiziert / abgelehnt

| # | Vorschlag | Ergebnis |
|---|---|---|
| 1 | Projekt-Grundgerüst | akzeptiert |
| 2 | Saisonale Abweichung ggü. Gesamtmittelwert | **abgelehnt/verworfen**, neu implementiert (Trend-Leakage-Bug) |
| 3 | AI-Client mit injizierbarem Transport | akzeptiert |
| 4 | Dashboard-Methodenanzeige | modifiziert (Formatierung) |
| 5 | Docker-Setup | akzeptiert, **build- und funktionsgetestet auf echtem Rechner** (Nachtrag 1: `.env`-vs-Docker-Netzwerk-Konflikt bei AI_BASE_URL gefunden und behoben; Nachtrag 2: eigener `ollama`-Service zugunsten eines projektübergreifend geteilten Host-Ollama entfernt, auf Wunsch des Studierenden) |
| 6 | Grounding-Fakten für Kraftstoffvergleich | akzeptiert (Erweiterung nach Evaluationsfund) |
| 7 | Warm-up-Aufruf + Groundedness-/Evaluations-Heuristik-Fixes | akzeptiert (drei reale, mit dem echten Modell gefundene Probleme behoben und verifiziert) |
| 8 | Fester Port pro Projekt + venv-Neuanlage (Python 3.12) | akzeptiert (Python-3.14-Inkompatibilitaet behoben; Port-Konflikt zwischen Docker-Container und nativem Prozess als wahre Ursache eines zunaechst als Netzwerk-/uvloop-Bug vermuteten Problems identifiziert) |
| 9 | Docker-Endverifikation (`.env`-Override-Fix) + Sammel-Infrastruktur fuer echte Tankerkoenig-Daten | akzeptiert (zweiter, unabhaengiger `.env`-Override-Bug in `docker-compose.yml` behoben; Client/Skripte/Tests fuer echte Preisdaten vorbereitet, mangels Registrierungs-Freigabe noch nicht live verifiziert) |
