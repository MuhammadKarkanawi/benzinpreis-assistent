import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.ai.client import AIClient
from app.data_loader import seed_from_csv
from app.db import get_session
from app.main import app
from app.routers.ask import get_ai_client
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(engine):
    data_dir = REPO_ROOT / "data"
    if not (data_dir / "stations.csv").exists():
        pytest.skip("Beispieldaten nicht generiert - vorher 'python -m scripts.generate_sample_data' ausführen.")

    with Session(engine) as s:
        seed_from_csv(s, data_dir)

    def _get_session_override():
        with Session(engine) as s:
            yield s

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Testantwort mit 1.700 EUR."}}]}
        )

    def _get_ai_client_override():
        from app.config import get_settings

        return AIClient(get_settings(), transport=httpx.MockTransport(handler))

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_ai_client] = _get_ai_client_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] is True


def test_list_stations(client):
    resp = client.get("/stations")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_price_history_for_unknown_station_returns_404(client):
    resp = client.get("/prices/does-not-exist?fuel_type=e5")
    assert resp.status_code == 404


def test_price_history_and_forecast_for_known_station(client):
    station_uuid = client.get("/stations").json()[0]["uuid"]

    resp = client.get(f"/prices/{station_uuid}?fuel_type=e5&days=14")
    assert resp.status_code == 200
    assert len(resp.json()["points"]) > 0

    resp = client.get(f"/forecast/{station_uuid}?fuel_type=e5&horizon_hours=24")
    assert resp.status_code == 200
    body = resp.json()
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["predicted_direction"] in ("steigend", "fallend", "stabil")


def test_ask_grounded_returns_answer_and_facts(client):
    station_uuid = client.get("/stations").json()[0]["uuid"]
    resp = client.post(
        "/ask",
        json={"station_uuid": station_uuid, "fuel_type": "e5", "question": "Wie ist der Preis?", "use_context": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["used_context"] is True
    assert body["grounding_facts"]["current_price_eur"] is not None
    assert body["error"] is None


def test_ask_without_context_returns_no_facts(client):
    station_uuid = client.get("/stations").json()[0]["uuid"]
    resp = client.post(
        "/ask",
        json={"station_uuid": station_uuid, "fuel_type": "e5", "question": "Wie ist der Preis?", "use_context": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["used_context"] is False
    assert body["grounding_facts"] == {}


def test_ask_unknown_station_reports_error_not_crash(client):
    resp = client.post(
        "/ask",
        json={"station_uuid": "unknown", "fuel_type": "e5", "question": "Wie ist der Preis?", "use_context": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is not None
