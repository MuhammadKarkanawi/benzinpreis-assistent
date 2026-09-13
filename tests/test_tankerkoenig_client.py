import httpx
import pytest

from app.integrations.tankerkoenig_client import (
    TankerkoenigClient,
    TankerkoenigInvalidResponseError,
    TankerkoenigUnavailableError,
)


def test_find_stations_nearby_normalizes_schema():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/json/list.php"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "stations": [
                    {
                        "id": "real-uuid-1",
                        "name": "Aral Tankstelle",
                        "brand": "Aral",
                        "street": "Musterstraße",
                        "houseNumber": "5",
                        "postCode": 44137,
                        "place": "Dortmund",
                        "lat": 51.5,
                        "lng": 7.46,
                        "dist": 1.2,
                        "diesel": 1.699,
                        "e5": 1.799,
                        "e10": 1.739,
                    }
                ],
            },
        )

    client = TankerkoenigClient(api_key="x", transport=httpx.MockTransport(handler))
    stations = client.find_stations_nearby(51.5136, 7.4653, radius_km=5.0)
    assert stations == [
        {
            "uuid": "real-uuid-1",
            "name": "Aral Tankstelle",
            "brand": "Aral",
            "street": "Musterstraße 5",
            "place": "Dortmund",
            "post_code": "44137",
            "latitude": 51.5,
            "longitude": 7.46,
        }
    ]


def test_current_prices_returns_raw_price_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/json/prices.php"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "prices": {
                    "real-uuid-1": {"status": "open", "e5": 1.799, "e10": 1.739, "diesel": 1.699}
                },
            },
        )

    client = TankerkoenigClient(api_key="x", transport=httpx.MockTransport(handler))
    prices = client.current_prices(["real-uuid-1"])
    assert prices["real-uuid-1"]["diesel"] == 1.699


def test_current_prices_rejects_more_than_ten_ids():
    client = TankerkoenigClient(api_key="x")
    with pytest.raises(ValueError):
        client.current_prices([f"id-{i}" for i in range(11)])


def test_current_prices_empty_list_returns_empty_dict_without_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Sollte bei leerer Liste keine Anfrage senden")

    client = TankerkoenigClient(api_key="x", transport=httpx.MockTransport(handler))
    assert client.current_prices([]) == {}


def test_raises_invalid_response_on_api_error_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "message": "ungültiger Key"})

    client = TankerkoenigClient(api_key="x", transport=httpx.MockTransport(handler))
    with pytest.raises(TankerkoenigInvalidResponseError):
        client.find_stations_nearby(51.5, 7.4)


def test_raises_unavailable_on_connect_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    client = TankerkoenigClient(api_key="x", transport=httpx.MockTransport(handler))
    with pytest.raises(TankerkoenigUnavailableError):
        client.find_stations_nearby(51.5, 7.4)


def test_raises_unavailable_on_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    client = TankerkoenigClient(api_key="x", transport=httpx.MockTransport(handler))
    with pytest.raises(TankerkoenigUnavailableError):
        client.find_stations_nearby(51.5, 7.4)
