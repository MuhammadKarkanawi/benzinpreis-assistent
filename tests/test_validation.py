from app.ai.validation import extract_decimal_numbers, is_grounded

FACTS = {
    "current_price_eur": 1.739,
    "forecast": {"predicted_price_eur": 1.755, "confidence_heuristic_0_to_1": 0.8},
}


def test_extract_decimal_numbers_handles_comma_and_dot():
    assert extract_decimal_numbers("Der Preis liegt bei 1,739 EUR und steigt auf 1.755 EUR.") == [1.739, 1.755]


def test_is_grounded_true_when_numbers_match_facts():
    text = "Der aktuelle Preis liegt bei 1.739 EUR, die Vorhersage liegt bei 1.755 EUR."
    assert is_grounded(text, FACTS) is True


def test_is_grounded_false_when_number_is_fabricated():
    text = "Der Preis wird auf 2.499 EUR steigen."
    assert is_grounded(text, FACTS) is False


def test_is_grounded_true_with_no_numbers_in_answer():
    text = "Der Preis bleibt voraussichtlich stabil."
    assert is_grounded(text, FACTS) is True


def test_is_grounded_false_when_ungrounded_but_claims_numbers():
    text = "Der Preis liegt bei 1.85 EUR."
    assert is_grounded(text, None) is False


def test_is_grounded_within_tolerance():
    text = "Der Preis liegt bei etwa 1.74 EUR."  # 1 Cent Differenz zu 1.739
    assert is_grounded(text, FACTS, tolerance=0.02) is True
