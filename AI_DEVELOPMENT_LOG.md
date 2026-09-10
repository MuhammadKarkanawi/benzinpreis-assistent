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
- **Konsequenz/Risiko:** Dockerfile und docker-compose.yml sind
  syntaktisch/strukturell geprüft, aber NICHT in dieser Umgebung
  build-getestet. **Vor der Abgabe muss `docker compose --profile mock up
  --build` bzw. mit `--profile real` einmal real auf einem Rechner mit
  Internetzugang ausgeführt und verifiziert werden.**

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

---

## Zusammenfassung: akzeptiert / modifiziert / abgelehnt

| # | Vorschlag | Ergebnis |
|---|---|---|
| 1 | Projekt-Grundgerüst | akzeptiert |
| 2 | Saisonale Abweichung ggü. Gesamtmittelwert | **abgelehnt/verworfen**, neu implementiert (Trend-Leakage-Bug) |
| 3 | AI-Client mit injizierbarem Transport | akzeptiert |
| 4 | Dashboard-Methodenanzeige | modifiziert (Formatierung) |
| 5 | Docker-Setup | akzeptiert, aber ungetestet - offene Aufgabe für den Studierenden markiert |
| 6 | Grounding-Fakten für Kraftstoffvergleich | akzeptiert (Erweiterung nach Evaluationsfund) |
