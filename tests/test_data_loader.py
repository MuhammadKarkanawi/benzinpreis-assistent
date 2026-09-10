from pathlib import Path

import pytest
from sqlmodel import select

from app.data_loader import load_price_series, seed_from_csv
from app.models import PriceRecord, Station

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_seed_from_csv_loads_generated_sample_data(session):
    data_dir = REPO_ROOT / "data"
    if not (data_dir / "stations.csv").exists():
        pytest.skip("Beispieldaten nicht generiert - vorher 'python -m scripts.generate_sample_data' ausführen.")

    result = seed_from_csv(session, data_dir)
    assert result["skipped"] is False
    assert result["n_stations"] == 3
    assert result["n_prices"] > 0

    stations = session.exec(select(Station)).all()
    assert len(stations) == 3

    # zweiter Aufruf ohne force -> soll übersprungen werden (keine Duplikate)
    result2 = seed_from_csv(session, data_dir)
    assert result2["skipped"] is True


def test_load_price_series_returns_sorted_non_null_values(session, sample_station):
    from datetime import datetime, timedelta

    session.add(sample_station)
    session.commit()
    base = datetime(2026, 1, 1)
    for i, price in enumerate([1.70, None, 1.72, 1.68]):
        session.add(
            PriceRecord(
                station_uuid=sample_station.uuid,
                timestamp=base + timedelta(hours=i),
                e5=price,
            )
        )
    session.commit()

    df = load_price_series(session, sample_station.uuid, "e5")
    assert list(df["e5"]) == [1.70, 1.72, 1.68]
    assert df["timestamp"].is_monotonic_increasing


def test_load_price_series_rejects_unknown_fuel_type(session):
    with pytest.raises(ValueError):
        load_price_series(session, "irrelevant", "super_plus")
