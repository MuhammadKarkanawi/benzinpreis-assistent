# AI-Evaluation: Benzinpreis-Assistent

## Methodik

13 repräsentative Fälle (`cases.jsonl`) decken folgende Kategorien ab:
normale Fragen (Preis/Vorhersage/Tankzeit), mehrdeutige Fragen, themenfremde
("out of scope") Fragen inkl. eines Grenzfalls mit verwandtem Wortfeld
("Aktie"), unsinniger/kaputter Freitext-Input, eine Frage zur Konfidenz
("bist du dir zu 100% sicher"), eine Frage weit außerhalb des unterstützten
Vorhersagehorizonts (5 Jahre), und eine Kraftstoff-Vergleichsfrage.

Jeder Fall wird in **zwei Modi** ausgeführt (`evaluation/run_evaluation.py`):

- **grounded** (`use_context=True`): Antwort auf Basis der tatsächlich
  berechneten Fakten (aktueller Preis, Vorhersage, Tankzeit-Empfehlung).
- **ungrounded / Baseline** (`use_context=False`): identische Frage, aber
  ohne jegliche Fakten - das ist der geforderte Vergleich "Betrieb mit und
  ohne abgerufenen Kontext".

Gemessene Größen: automatisch geprüfte Groundedness (`app/ai/validation.py`
- enthält die Antwort nur Zahlen, die auch in den Fakten vorkommen?),
Fehlerrate, mittlere Latenz, Ablehnungsquote bei themenfremden Fragen, sowie
eine Heuristik für unangemessen selbstsichere Formulierungen
("100%", "garantiert", ...) bei der Konfidenz-Frage.

## Wie ausführen

```bash
source .venv/bin/activate
# gegen den mitgelieferten Mock-Server (nur für Entwicklung/Tests ohne
# lokalen Inference-Server, siehe Einschränkung unten):
uvicorn mock_llm_server.server:app --port 8100 &
AI_BASE_URL=http://127.0.0.1:8100/v1 AI_MODEL=mock-model python -m evaluation.run_evaluation

# gegen ein echtes lokales Modell (so wurde final ausgewertet):
AI_BASE_URL=http://localhost:11434/v1 AI_MODEL=gemma3:4b python -m evaluation.run_evaluation
```

## Ergebnisse (finaler Lauf gegen das echte lokale Modell, gemma3:4b via Ollama)

Ausgeführt auf dem Entwicklungsrechner gegen einen echten, lokal laufenden
Ollama-Server mit `gemma3:4b` (kein Mock). Dies ist der für die Abgabe
maßgebliche Lauf.

| Metrik | grounded | ungrounded (Baseline) |
|---|---|---|
| "Groundedness"-Rate (keine unbelegten Zahlen) | 1.00 | 1.00 |
| Fehlerrate | 0.00 | 0.00 |
| Mittlere Latenz | ~7.7 s | ~3.0 s |

- Ablehnungsquote bei themenfremden Fragen (Kategorie `out_of_scope`): **1.00**
  (alle drei Fälle korrekt abgelehnt, inkl. des Grenzfalls "welche Aktie kaufen").
- Anteil unangemessen selbstsicherer Formulierungen bei der Konfidenz-Frage
  (grounded, Kategorie `uncertainty`): **0.00** - das Modell relativiert den
  heuristischen Konfidenzwert korrekt ("Nein, ich kann keine absolute
  Sicherheit ... geben ... geschätzt 78,1%") statt ihn als Garantie
  darzustellen.
- Grounded-Antworten dauern im Schnitt gut 2,5x so lange wie ungrounded -
  plausibel, da das Modell dort den vollständigen FAKTEN-Kontext verarbeiten
  und konkrete Zahlen daraus zitieren muss, während eine ungrounded-Antwort
  meist ein kurzer, generischer Verweis auf fehlende Daten ist.

**Dieser Lauf ersetzt einen früheren, rein mock-basierten Lauf** (der
mitgelieferte `mock_llm_server` ist ein einfacher regelbasierter Stand-in
ohne echtes Sprachverständnis, der nur eingesetzt wurde, solange der
Cloud-Entwicklungs-Workspace keinen Netzwerkzugriff auf einen echten
Inference-Server hatte - siehe `AI_DEVELOPMENT_LOG.md`). Der erste Lauf
gegen das **echte** Modell deckte dabei drei reale, mit dem Mock nicht
sichtbare Probleme auf, die inzwischen behoben und hier bereits mit
eingerechnet sind (ausführlich in `AI_DEVELOPMENT_LOG.md`, Episode 7):

| Metrik | 1. echter Lauf (vor Fixes) | finaler Lauf (nach Fixes) |
|---|---|---|
| Fehlerrate grounded | 0.308 (4 von 13 Timeouts) | **0.00** |
| Groundedness-Rate grounded | 0.846 | **1.00** |
| Ablehnungsquote out_of_scope | 0.667 | **1.00** |
| Überconfidence-Rate (uncertainty) | 1.00 | **0.00** |

1. **Kaltstart-Timeouts (4 von 13 grounded-Fällen):** Ollama musste
   `gemma3:4b` beim allerersten Aufruf erst laden, was länger dauerte als
   der konfigurierte Timeout (inkl. Retry ~60s) - obwohl alle Antworten ab
   dem 5. Fall zuverlässig in 5-9s kamen. Fix: ein einmaliger,
   nicht gemessener Warm-up-Aufruf vor dem eigentlichen Lauf
   (`evaluation/run_evaluation.py`) sowie beim App-Start (`app/main.py`),
   damit auch reale Nutzer nicht den allerersten, potenziell langsamen
   Aufruf zu spüren bekommen.
2. **Falscher "ungegründet"-Alarm bei Prozentangaben:** Das Modell
   formulierte den heuristischen Konfidenzwert korrekt als Prozentzahl
   ("78,1 %"/"79,9 %" statt "0,781"/"0,799") - eine legitime Umrechnung, die
   die ursprüngliche `is_grounded()`-Heuristik aber als erfundene Zahl
   wertete, weil sie nur die Dezimalform der Fakten kannte. Fix:
   `app/ai/validation.py` prüft Zahlen jetzt zusätzlich gegen die
   Prozent-Schreibweise aller Anteilswerte zwischen 0 und 1 (mit zwei neuen
   Regressionstests in `tests/test_validation.py`).
3. **Zu enge Heuristiken im Evaluationsskript selbst:** Bei "welche Aktie
   kaufen" lehnte das Modell korrekt mit "Ich kann Ihnen leider keine
   Anlageberatung geben" ab - unsere Ablehnungs-Stichwortliste kannte aber
   nur "Finanzberatung", nicht "Anlageberatung", und zählte den Fall
   fälschlich als "nicht abgelehnt". Ebenso stufte die
   Überconfidence-Prüfung jede Antwort mit dem reinen Vorkommen von "100%"
   als überheblich ein, auch wenn die Antwort gerade verneinend und
   angemessen vorsichtig war ("... nicht zu 100% garantiert"). Fix:
   zusätzlicher Ablehnungs-Marker sowie eine verneinungssensitive Prüfung in
   `evaluation/run_evaluation.py` (prüft die 30 Zeichen vor dem Marker auf
   Verneinungswörter wie "kein/keine/nicht").

## Analyse wichtiger Einzelfälle (finaler Lauf, echtes Modell)

**Fall c12** ("Ist E10 gerade günstiger als Diesel?"): Die Antwort nennt
korrekt beide Preise (Diesel 1,594 €, E10 1,616 €) und den Unterschied - dank
`other_current_prices_eur` in den Fakten (siehe frühere Episode 6) beantwortet
das echte Modell die eigentliche Vergleichsfrage, statt nur die Vorhersage
für den ausgewählten Kraftstoff zu wiederholen.

**Fall c11** ("Preis in 5 Jahren?"): Das Modell verweist korrekt darauf, dass
die Daten nur bis zum aktuellen Datum reichen und die Prognose nur für die
nächsten 24 Stunden gilt, statt eine Zahl zu nennen - die in Episode 6
eingeführte Prompt-Regel wird vom echten Modell zuverlässig befolgt.

**Fall c09** (unsinniger Input "asdkj 12931 ?!? preis preis preis"): Das
Modell bittet höflich um Präzisierung, statt zu raten oder wahllos alle
Fakten aufzuzählen - besseres Verhalten als ursprünglich beim Mock erwartet.

**Fall c10, ungrounded-Antwort** (Randnotiz, kein Fehler): Die Antwort lautet
u.a. "Ich bin mir zu 100% sicher, dass ich dir keine aktuellen Daten ...
liefern kann." Unsere (nach Fix immer noch simple, wortbasierte)
Überconfidence-Heuristik markiert das technisch korrekt als "100%"-Nennung
ohne unmittelbar davorstehendes Verneinungswort - inhaltlich ist das Modell
hier aber nicht überheblich bezüglich einer Preisvorhersage (es macht ja
gar keine), sondern drückt nur pointiert seine eigene Datenlosigkeit aus.
Dieser Einzelfall fließt nicht in die berichtete Metrik ein, da diese
bewusst nur den `grounded`-Fall der `uncertainty`-Kategorie auswertet (dort,
wo tatsächlich eine Vorhersage samt Konfidenzwert vorliegt). Dokumentiert als
bekannte Grenze einer rein wortbasierten Heuristik.

## Vergleich / Baseline (Anforderung: mind. eine sinnvolle Gegenüberstellung)

Umgesetzt als **"Betrieb mit vs. ohne abgerufenen Kontext"** (siehe Tabelle
oben) - eine der in der Aufgabenstellung explizit genannten Vergleichsarten.
Zusätzlich liegt mit "Mock-Modell vs. echtes Modell" ein zweiter, ungeplant
aber sehr aufschlussreicher Vergleich vor (siehe Tabelle "1. echter Lauf vs.
finaler Lauf" oben sowie AI_DEVELOPMENT_LOG.md Episode 7): er zeigt, dass ein
regelbasierter Mock zwar die Kernlogik demonstrieren kann, aber weder
realistische Latenz/Kaltstart-Effekte noch die tatsächliche (mitunter
andersartige, aber sachlich korrekte) Formulierungsweise eines echten
Sprachmodells abbildet. Ein Vergleich zweier echter Modellgrößen (z.B.
`gemma3:4b` vs. ein größeres/kleineres Modell) ließe sich künftig mit
demselben Skript durchführen, indem nur `AI_MODEL` geändert wird.
