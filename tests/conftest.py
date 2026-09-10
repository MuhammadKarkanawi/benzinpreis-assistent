from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models import PriceRecord, Station


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def sample_station() -> Station:
    return Station(
        uuid="test-station-1",
        name="Testtankstelle",
        brand="Testmarke",
        street="Teststraße 1",
        place="Testhausen",
        post_code="12345",
        latitude=51.0,
        longitude=7.0,
    )


def make_price_series(n_days: int = 30, base_price: float = 1.70, trend_per_day: float = 0.0) -> pd.DataFrame:
    """Erzeugt eine deterministische, einfache Preiszeitreihe (stündlich) für
    Unit-Tests von forecasting.py - bewusst ohne Zufall, damit Tests
    reproduzierbar sind."""
    import math

    start = datetime(2026, 1, 1)
    rows = []
    for h in range(n_days * 24):
        ts = start + timedelta(hours=h)
        day = h // 24
        daily_wave = 0.03 * math.cos((ts.hour - 8) / 24.0 * 2 * math.pi)
        price = base_price + trend_per_day * day + daily_wave
        rows.append({"timestamp": ts, "e5": round(price, 3)})
    return pd.DataFrame(rows)
