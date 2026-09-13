from sqlmodel import SQLModel, Session, create_engine, select

from app.config import Settings
from app.models import PriceRecord
from scripts import collect_real_prices


def make_settings(**overrides) -> Settings:
    defaults = dict(tankerkoenig_api_key="key", tankerkoenig_station_uuids="real-uuid-1")
    defaults.update(overrides)
    return Settings(**defaults)


def _fresh_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_collect_skips_without_api_key(monkeypatch):
    monkeypatch.setattr(collect_real_prices, "get_settings", lambda: make_settings(tankerkoenig_api_key=""))
    result = collect_real_prices.collect()
    assert result["skipped"] is True


def test_collect_skips_without_station_uuids(monkeypatch):
    monkeypatch.setattr(collect_real_prices, "get_settings", lambda: make_settings(tankerkoenig_station_uuids=""))
    result = collect_real_prices.collect()
    assert result["skipped"] is True


def test_collect_inserts_price_record_and_marks_first_value_as_change(monkeypatch):
    engine = _fresh_engine()
    monkeypatch.setattr(collect_real_prices, "engine", engine)
    monkeypatch.setattr(collect_real_prices, "get_settings", lambda: make_settings())
    monkeypatch.setattr(collect_real_prices, "init_db", lambda: None)

    class FakeClient:
        def __init__(self, api_key):
            pass

        def current_prices(self, ids):
            return {"real-uuid-1": {"status": "open", "e5": 1.799, "e10": 1.739, "diesel": 1.699}}

    monkeypatch.setattr(collect_real_prices, "TankerkoenigClient", FakeClient)

    result = collect_real_prices.collect()
    assert result == {"skipped": False, "n_inserted": 1, "timestamp": result["timestamp"]}

    with Session(engine) as session:
        records = session.exec(select(PriceRecord)).all()
    assert len(records) == 1
    assert records[0].diesel == 1.699
    # Erster jemals gespeicherter Wert - gilt als "Aenderung" (kein Vorwert vorhanden)
    assert records[0].diesel_change == 1
    assert records[0].e5_change == 1
    assert records[0].e10_change == 1


def test_collect_marks_unchanged_price_as_no_change_on_second_run(monkeypatch):
    engine = _fresh_engine()
    monkeypatch.setattr(collect_real_prices, "engine", engine)
    monkeypatch.setattr(collect_real_prices, "get_settings", lambda: make_settings())
    monkeypatch.setattr(collect_real_prices, "init_db", lambda: None)

    same_prices = {"real-uuid-1": {"status": "open", "e5": 1.799, "e10": 1.739, "diesel": 1.699}}

    class FakeClient:
        def __init__(self, api_key):
            pass

        def current_prices(self, ids):
            return same_prices

    monkeypatch.setattr(collect_real_prices, "TankerkoenigClient", FakeClient)

    collect_real_prices.collect()
    result = collect_real_prices.collect()
    assert result["n_inserted"] == 1

    with Session(engine) as session:
        records = session.exec(select(PriceRecord).order_by(PriceRecord.id)).all()
    assert len(records) == 2
    assert records[1].diesel_change == 0
    assert records[1].e5_change == 0
    assert records[1].e10_change == 0


def test_collect_skips_station_reported_as_no_prices(monkeypatch):
    engine = _fresh_engine()
    monkeypatch.setattr(collect_real_prices, "engine", engine)
    monkeypatch.setattr(collect_real_prices, "get_settings", lambda: make_settings())
    monkeypatch.setattr(collect_real_prices, "init_db", lambda: None)

    class FakeClient:
        def __init__(self, api_key):
            pass

        def current_prices(self, ids):
            return {"real-uuid-1": {"status": "no prices"}}

    monkeypatch.setattr(collect_real_prices, "TankerkoenigClient", FakeClient)

    result = collect_real_prices.collect()
    assert result["n_inserted"] == 0

    with Session(engine) as session:
        records = session.exec(select(PriceRecord)).all()
    assert len(records) == 0
