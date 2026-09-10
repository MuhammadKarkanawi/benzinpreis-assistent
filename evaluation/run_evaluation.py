"""
Führt die in cases.jsonl definierten Evaluationsfälle gegen die konfigurierte
KI-Komponente aus (echter lokaler Inference-Server ODER der Mock-Server aus
mock_llm_server/, je nachdem was in AI_BASE_URL/AI_MODEL konfiguriert ist -
der Code hier ändert sich nicht).

Für jeden Fall wird sowohl der gegründete Modus (use_context=True) als auch
der Baseline-Modus ohne Kontext (use_context=False) ausgeführt - das ist der
in der Aufgabenstellung geforderte Vergleich "mit vs. ohne gestützten
Kontext".

Ausgabe:
- evaluation/results/summary.json   (aggregierte Metriken, maschinenlesbar)
- evaluation/results/details.jsonl  (Einzel-Ergebnisse je Fall/Modus)

Ausführen mit (aus dem Projekt-Wurzelverzeichnis, venv aktiv):
    python -m evaluation.run_evaluation
"""
from __future__ import annotations

import asyncio
import csv
import json
import statistics
import time
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.ai.client import AIClient
from app.ai.qa import answer_question
from app.config import get_settings
from app.data_loader import seed_from_csv

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = REPO_ROOT / "evaluation" / "results"
CASES_PATH = REPO_ROOT / "evaluation" / "cases.jsonl"

REFUSAL_MARKERS = [
    "kann ich nicht", "keine auskunft", "außerhalb", "nur zu kraftstoffpreisen",
    "nur für kraftstoffpreise", "dazu kann ich leider nichts sagen", "bin ich nicht zuständig",
    "kann ich dir nicht", "keine finanzberatung", "nicht mein themenbereich",
]

OVERCONFIDENT_MARKERS = ["100%", "garantiert", "sicher richtig", "auf jeden fall"]


def load_station_map() -> dict[str, str]:
    with (DATA_DIR / "stations.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # s1 -> erste Zeile, s2 -> zweite, s3 -> dritte (Reihenfolge wie generiert)
    return {f"s{i+1}": row["uuid"] for i, row in enumerate(rows)}


def load_cases() -> list[dict]:
    cases = []
    with CASES_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def looks_like_refusal(answer: str) -> bool:
    a = answer.lower()
    return any(marker in a for marker in REFUSAL_MARKERS)


def looks_overconfident(answer: str) -> bool:
    a = answer.lower()
    return any(marker in a for marker in OVERCONFIDENT_MARKERS)


async def run() -> dict:
    settings = get_settings()
    station_map = load_station_map()
    cases = load_cases()

    # Eigene, isolierte In-Memory-Datenbank für die Evaluation - unabhängig
    # von einer evtl. bereits laufenden App-Instanz.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_from_csv(session, DATA_DIR)

    ai_client = AIClient(settings)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    details_path = RESULTS_DIR / "details.jsonl"

    details = []
    with Session(engine) as session, details_path.open("w", encoding="utf-8") as details_file:
        for case in cases:
            station_uuid = station_map[case["station"]]
            for use_context in (True, False):
                t0 = time.perf_counter()
                result = await answer_question(
                    session=session,
                    settings=settings,
                    ai_client=ai_client,
                    station_uuid=station_uuid,
                    fuel_type=case["fuel_type"],
                    question=case["question"],
                    use_context=use_context,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000

                record = {
                    "case_id": case["id"],
                    "category": case["category"],
                    "question": case["question"],
                    "use_context": use_context,
                    "answer": result["answer"],
                    "error": result["error"],
                    "flagged_ungrounded": result["flagged_ungrounded"],
                    "latency_ms": round(elapsed_ms, 1),
                    "is_refusal": looks_like_refusal(result["answer"]),
                    "is_overconfident": looks_overconfident(result["answer"]),
                }
                details.append(record)
                details_file.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = summarize(details)
    (RESULTS_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def summarize(details: list[dict]) -> dict:
    def mode_subset(use_context: bool) -> list[dict]:
        return [d for d in details if d["use_context"] == use_context]

    def error_rate(subset: list[dict]) -> float:
        return sum(1 for d in subset if d["error"]) / len(subset) if subset else 0.0

    def grounded_rate(subset: list[dict]) -> float:
        # Anteil OHNE Flag = "wirkt gegruendet"
        return sum(1 for d in subset if not d["flagged_ungrounded"]) / len(subset) if subset else 0.0

    def mean_latency(subset: list[dict]) -> float:
        vals = [d["latency_ms"] for d in subset if d["error"] is None]
        return round(statistics.mean(vals), 1) if vals else 0.0

    out_of_scope = [d for d in details if d["category"] == "out_of_scope" and d["use_context"]]
    refusal_rate_out_of_scope = (
        sum(1 for d in out_of_scope if d["is_refusal"]) / len(out_of_scope) if out_of_scope else None
    )

    uncertainty = [d for d in details if d["category"] == "uncertainty" and d["use_context"]]
    overconfident_rate = (
        sum(1 for d in uncertainty if d["is_overconfident"]) / len(uncertainty) if uncertainty else None
    )

    grounded_mode = mode_subset(True)
    ungrounded_mode = mode_subset(False)

    return {
        "n_cases": len({d["case_id"] for d in details}),
        "n_runs": len(details),
        "grounded_mode": {
            "grounded_rate": round(grounded_rate(grounded_mode), 3),
            "error_rate": round(error_rate(grounded_mode), 3),
            "mean_latency_ms": mean_latency(grounded_mode),
        },
        "ungrounded_baseline_mode": {
            "grounded_rate": round(grounded_rate(ungrounded_mode), 3),
            "error_rate": round(error_rate(ungrounded_mode), 3),
            "mean_latency_ms": mean_latency(ungrounded_mode),
        },
        "comparison_note": (
            "Vergleich 'mit vs. ohne gestuetzten Kontext' (siehe Anforderung Baseline-Vergleich). "
            "Mit dem beiliegenden Mock-Modell antwortet der ungrounded-Modus meist ehrlich mit "
            "'keine Daten vorhanden' (dadurch ebenfalls hoher grounded_rate-Wert nach unserer "
            "Zahlen-Heuristik, da schlicht keine Zahlen genannt werden). Mit einem echten lokalen "
            "Sprachmodell ist zu erwarten, dass der ungrounded-Modus deutlich haeufiger Zahlen "
            "erfindet - dieser Lauf sollte vor der Abgabe mit dem echten Modell wiederholt werden."
        ),
        "off_topic_refusal_rate": (
            round(refusal_rate_out_of_scope, 3) if refusal_rate_out_of_scope is not None else None
        ),
        "overconfident_rate_on_uncertainty_questions": (
            round(overconfident_rate, 3) if overconfident_rate is not None else None
        ),
    }


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False, indent=2))
