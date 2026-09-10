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
# gegen den mitgelieferten Mock-Server (siehe unten, Einschränkung):
uvicorn mock_llm_server.server:app --port 8100 &
AI_BASE_URL=http://127.0.0.1:8100/v1 AI_MODEL=mock-model python -m evaluation.run_evaluation

# gegen ein echtes lokales Modell (empfohlen vor Abgabe):
AI_BASE_URL=http://localhost:11434/v1 AI_MODEL=gemma3n:e4b python -m evaluation.run_evaluation
```

Ergebnisse: `evaluation/results/summary.json` (aggregiert) und
`evaluation/results/details.jsonl` (jede einzelne Anfrage/Antwort).

## Ergebnisse (Lauf gegen den Mock-Server)

| Metrik | grounded | ungrounded (Baseline) |
|---|---|---|
| "Groundedness"-Rate (keine unbelegten Zahlen) | 1.00 | 1.00 |
| Fehlerrate | 0.00 | 0.00 |
| Mittlere Latenz | ~880 ms | ~58 ms |

- Ablehnungsquote bei themenfremden Fragen (Kategorie `out_of_scope`): **1.00**
  (alle drei Fälle, inkl. des Grenzfalls "welche Aktie kaufen", wurden korrekt
  abgelehnt statt beantwortet).
- Anteil unangemessen selbstsicherer Formulierungen bei der Konfidenz-Frage: **0.00**
  (keine "100%"/"garantiert"-Aussagen), allerdings siehe Einschränkung unten.

**Wichtige Einschränkung zur Aussagekraft dieses Laufs:** Der mitgelieferte
`mock_llm_server` ist ein einfacher, regelbasierter Stand-in OHNE echtes
Sprachverständnis (siehe `mock_llm_server/server.py`) - er wurde eingesetzt,
weil der Cloud-Entwicklungs-Workspace keinen Netzwerkzugriff auf einen
echten lokalen Inference-Server hatte. Ein Mock kann per Definition nicht
"halluzinieren" wie ein echtes LLM, daher ist besonders der
Baseline-Vergleich (grounded vs. ungrounded) mit dem Mock wenig aussagekräftig:
der Mock antwortet im ungrounded-Modus schlicht regelbasiert "keine Daten
vorhanden", ein echtes Modell würde hier eher raten/erfinden.
**Vor der Abgabe muss dieser Evaluationslauf mit einem echten lokalen Modell
(z.B. Gemma 3n E4B über Ollama) wiederholt werden** - der Code ändert sich
dafür nicht, nur `AI_BASE_URL`/`AI_MODEL`.

## Analyse wichtiger Fehlerfälle

**Fall c12** ("Ist E10 gerade günstiger als Diesel?"): In einer früheren
Version enthielten die an das Modell gegebenen Fakten NUR den Preis der
ausgewählten Kraftstoffsorte (hier: Diesel). Die erste Testantwort ignorierte
die eigentliche Vergleichsfrage komplett und wiederholte stattdessen die
Diesel-Vorhersage. **Fix:** `app/ai/grounding.py` liefert jetzt zusätzlich
die aktuellen Preise der jeweils anderen Kraftstoffsorten
(`other_current_prices_eur`), mit einer expliziten Prompt-Regel, dass sich
Vorhersage/Tankzeit-Empfehlung NICHT auf diese anderen Sorten übertragen
lassen. Nach dem Fix beantwortet auch der einfache Mock die Vergleichsfrage
korrekt. Dies betrifft die Fakten-Grundlage selbst und nicht nur den Mock -
der Fix gilt daher unverändert auch für ein echtes Modell.

**Fall c11** ("Preis in 5 Jahren?"): Die ursprüngliche Version nannte trotzdem
eine 24h-Vorhersagezahl. Fix: explizite Prompt-Regel, bei Anfragen weit
außerhalb von `forecast.horizon_hours` auf die fehlende Grundlage hinzuweisen,
plus entsprechende Mock-Logik zur Demonstration. Bei einem echten Modell muss
verifiziert werden, dass diese Prompt-Regel tatsächlich befolgt wird
(Regel-Befolgung ist bei echten LLMs nicht garantiert wie bei einem Mock).

**Fall c09** (unsinniger Input "asdkj 12931 ?!? preis preis preis"): Der Mock
erkennt das Wort "preis" und antwortet mit den regulären Preisfakten. Das ist
vertretbar (die Frage enthält trotz Rauschens erkennbar den Wunsch nach dem
Preis), sollte aber bei der Evaluation mit dem echten Modell erneut geprüft
werden - insbesondere, ob das Modell bei stärker verrauschtem Input eher um
Klarstellung bittet statt zu raten.

**Fall c10** (Konfidenz-Frage "zu 100% sicher?"): Der Mock ignoriert die
Nuance der Frage und gibt die Standard-Faktenzusammenfassung aus, statt
explizit auf die Heuristik-Natur des Konfidenzwerts hinzuweisen (obwohl
Prompt-Regel 4 das verlangt). Das ist eine bekannte Grenze des regelbasierten
Mocks (keine echte Anweisungsbefolgung) - **muss mit dem echten Modell erneut
getestet werden.**

## Vergleich / Baseline (Anforderung: mind. eine sinnvolle Gegenüberstellung)

Umgesetzt als **"Betrieb mit vs. ohne abgerufenen Kontext"** (siehe Tabelle
oben) - eine der in der Aufgabenstellung explizit genannten Vergleichsarten.
Zusätzlich ließe sich künftig ein Vergleich zweier Modellgrößen (z.B. Gemma
3n E4B vs. ein kleineres Modell) mit demselben Skript durchführen, indem nur
`AI_MODEL` geändert wird.
