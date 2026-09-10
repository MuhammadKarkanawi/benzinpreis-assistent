import math
from datetime import datetime

import pandas as pd
import pytest

from app import forecasting
from tests.conftest import make_price_series


def test_forecast_raises_on_empty_data():
    df = pd.DataFrame({"timestamp": [], "e5": []})
    with pytest.raises(forecasting.InsufficientDataError):
        forecasting.forecast(df, "e5", horizon_hours=24)


def test_forecast_raises_when_history_too_short():
    df = make_price_series(n_days=3)
    with pytest.raises(forecasting.InsufficientDataError):
        forecasting.forecast(df, "e5", horizon_hours=24, min_history_days=7)


def test_forecast_detects_rising_trend():
    df = make_price_series(n_days=30, trend_per_day=0.01)  # klar steigend
    point = forecasting.forecast(df, "e5", horizon_hours=24, min_history_days=7)
    assert point.direction == "steigend"
    assert point.predicted_price > df["e5"].iloc[-1]


def test_forecast_detects_falling_trend():
    df = make_price_series(n_days=30, trend_per_day=-0.01)
    point = forecasting.forecast(df, "e5", horizon_hours=24, min_history_days=7)
    assert point.direction == "fallend"


def test_forecast_confidence_in_valid_range():
    df = make_price_series(n_days=30)
    point = forecasting.forecast(df, "e5", horizon_hours=24, min_history_days=7)
    assert 0.0 <= point.confidence <= 1.0


def test_validate_and_clean_drops_implausible_prices():
    df = make_price_series(n_days=10)
    df.loc[5, "e5"] = 99.0  # unplausibel
    df.loc[6, "e5"] = -1.0  # unplausibel (fehlender Wert im Originalformat)
    cleaned = forecasting.validate_and_clean(df, "e5")
    assert len(cleaned) == len(df) - 2
    assert cleaned.attrs["n_dropped_implausible"] == 2


def test_best_refuel_window_within_horizon():
    df = make_price_series(n_days=30)
    now = df["timestamp"].max()
    window = forecasting.best_refuel_window(df, "e5", now=now, horizon_hours=48, min_history_days=7)
    assert window.start >= now
    assert window.end <= now + pd.Timedelta(hours=49)
    assert window.start <= window.end


def test_seasonal_profile_picks_up_daily_pattern():
    df = make_price_series(n_days=30)
    profile = forecasting.compute_seasonal_profile(df, "e5")
    # Laut make_price_series liegt der Tiefpunkt der Kosinuswelle bei Stunde 20 (8+12)
    # und der Peak bei Stunde 8 - die Abweichung bei Stunde 8 muss klar positiver sein
    # als bei Stunde 20, für praktisch jeden Wochentag.
    for weekday in range(7):
        if (weekday, 8) in profile.by_weekday_hour and (weekday, 20) in profile.by_weekday_hour:
            assert profile.by_weekday_hour[(weekday, 8)] > profile.by_weekday_hour[(weekday, 20)]
