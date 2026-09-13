"""Heuristische Prüfung, ob eine KI-Antwort ausschließlich Zahlen enthält,
die auch tatsächlich in den gelieferten Fakten vorkommen ("Groundedness").

Dies ist bewusst eine einfache, erklärbare Heuristik und KEINE exakte
Garantie - sie dient als automatisiertes Warnsignal (flagged_ungrounded)
und als Baustein der AI-Evaluation (siehe evaluation/run_evaluation.py).
"""
from __future__ import annotations

import re
from typing import Iterable

NUMBER_PATTERN = re.compile(r"\d+[.,]\d+")
TOLERANCE_EUR = 0.02


def _flatten_numbers(obj) -> Iterable[float]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_numbers(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _flatten_numbers(v)
    elif isinstance(obj, (int, float)):
        yield float(obj)


def extract_decimal_numbers(text: str) -> list[float]:
    found = []
    for match in NUMBER_PATTERN.findall(text):
        normalized = match.replace(",", ".")
        try:
            found.append(float(normalized))
        except ValueError:
            continue
    return found


def _expand_with_percentage_form(numbers: list[float]) -> list[float]:
    """Ergänzt Fakten-Zahlen, die als Anteil 0-1 vorliegen (z.B. ein
    heuristischer Konfidenzwert `0.781`), um ihre Prozent-Schreibweise
    (`78.1`). Ein Sprachmodell formuliert einen solchen Wert in einer
    deutschen Antwort erfahrungsgemäß eher als "78,1 %" statt als "0,781" -
    das ist eine legitime, korrekte Umrechnung und keine erfundene Zahl.
    Ohne diese Erweiterung würde `is_grounded()` solche (korrekten!)
    Prozentangaben fälschlich als nicht gegründet einstufen (in der
    Praxis beobachtet, siehe AI_DEVELOPMENT_LOG.md Episode 7)."""
    expanded = list(numbers)
    for k in numbers:
        if 0.0 <= k <= 1.0:
            expanded.append(round(k * 100, 4))
    return expanded


def is_grounded(answer_text: str, facts: dict | None, tolerance: float = TOLERANCE_EUR) -> bool:
    """Gibt True zurück, wenn alle im Antworttext gefundenen Dezimalzahlen
    (typischerweise Preise) innerhalb der Toleranz zu einer Zahl aus den
    Fakten passen. Bei fehlenden Fakten (ungrounded-Modus) wird nur geprüft,
    dass GAR KEINE Preis-artigen Zahlen behauptet werden."""
    numbers_in_answer = extract_decimal_numbers(answer_text)
    if not numbers_in_answer:
        return True

    known_numbers = list(_flatten_numbers(facts)) if facts else []
    if not known_numbers:
        return False
    known_numbers = _expand_with_percentage_form(known_numbers)

    for n in numbers_in_answer:
        if not any(abs(n - k) <= tolerance for k in known_numbers):
            return False
    return True
