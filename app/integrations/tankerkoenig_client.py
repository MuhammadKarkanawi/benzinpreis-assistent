"""
Dünner Client für die öffentliche Tankerkönig-API
(https://creativecommons.tankerkoenig.de), analog zu app/ai/client.py
aufgebaut (injizierbarer httpx-Transport für Tests, explizite
Fehlerklassen).

STATUS DIESES MODULS:
Zum Zeitpunkt der ursprünglichen Entwicklung war die Registrierung für einen
neuen Tankerkönig-API-Key über die offizielle Seite
(onboarding.tankerkoenig.de) wegen Wartungsarbeiten des Anbieters nicht
möglich - der Client wurde deshalb zunächst ausschließlich gegen die
öffentlich dokumentierte API-Form geschrieben und nur mit
`httpx.MockTransport` getestet (siehe AI_DEVELOPMENT_LOG.md, Episode 9).
Inzwischen liegt ein echter API-Key vor und der Client wurde erfolgreich
gegen die echte, laufende API verifiziert (reale Preise, korrektes Schema -
siehe Episode 10). Dabei aufgefallen und behoben: ein zu knapper, fest
codierter Timeout (führte zu einem echten Timeout im Betrieb - jetzt über
`Settings.tankerkoenig_timeout_seconds` konfigurierbar) sowie Stationen, die
mit einem Status ungleich "no prices" trotzdem keine Preise liefern (z.B.
vorübergehend geschlossen) - wird von `scripts/collect_real_prices.py`
inzwischen konsistent übersprungen.

API-Endpunkte (Basis-URL: https://creativecommons.tankerkoenig.de/json/):
- list.php   : Tankstellen im Umkreis (lat, lng, rad, type, sort, apikey)
- prices.php : aktuelle Preise für bis zu 10 Tankstellen-IDs (ids, apikey)
"""
from __future__ import annotations

import httpx

TANKERKOENIG_BASE_URL = "https://creativecommons.tankerkoenig.de/json"


class TankerkoenigError(Exception):
    """Basisklasse für alle Fehler dieses Clients."""


class TankerkoenigUnavailableError(TankerkoenigError):
    pass


class TankerkoenigInvalidResponseError(TankerkoenigError):
    pass


class TankerkoenigClient:
    def __init__(self, api_key: str, transport: httpx.HTTPTransport | None = None, timeout: float = 15.0):
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout

    def find_stations_nearby(
        self, lat: float, lng: float, radius_km: float = 5.0, fuel_type: str = "all"
    ) -> list[dict]:
        """Sucht echte Tankstellen im Umkreis. Gibt eine Liste normalisierter
        Stations-Dicts zurück (Schema wie app.models.Station, ohne 'id')."""
        params = {
            "lat": lat,
            "lng": lng,
            "rad": radius_km,
            "type": fuel_type,
            "sort": "dist",
            "apikey": self._api_key,
        }
        data = self._get("list.php", params)
        if not data.get("ok", False):
            raise TankerkoenigInvalidResponseError(f"API meldete Fehler: {data.get('message', data)}")
        stations = []
        for raw in data.get("stations", []):
            stations.append(self._normalize_station(raw))
        return stations

    def current_prices(self, station_uuids: list[str]) -> dict[str, dict]:
        """Aktuelle Preise für bis zu 10 Stations-UUIDs. Gibt
        {uuid: {"e5": .., "e10": .., "diesel": .., "status": ..}} zurück."""
        if not station_uuids:
            return {}
        if len(station_uuids) > 10:
            raise ValueError("Tankerkönig prices.php erlaubt maximal 10 IDs pro Aufruf.")
        params = {"ids": ",".join(station_uuids), "apikey": self._api_key}
        data = self._get("prices.php", params)
        if not data.get("ok", False):
            raise TankerkoenigInvalidResponseError(f"API meldete Fehler: {data.get('message', data)}")
        return data.get("prices", {})

    def _get(self, path: str, params: dict) -> dict:
        url = f"{TANKERKOENIG_BASE_URL}/{path}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.get(url, params=params)
            if response.status_code >= 500:
                raise TankerkoenigUnavailableError(f"Tankerkönig-API antwortete mit Status {response.status_code}")
            if response.status_code >= 400:
                raise TankerkoenigInvalidResponseError(
                    f"Tankerkönig-API lehnte Anfrage ab (Status {response.status_code}): {response.text[:300]}"
                )
            return response.json()
        except httpx.TimeoutException as exc:
            raise TankerkoenigUnavailableError(f"Zeitüberschreitung beim Aufruf der Tankerkönig-API: {exc}") from exc
        except httpx.ConnectError as exc:
            raise TankerkoenigUnavailableError(f"Tankerkönig-API nicht erreichbar unter {url}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise TankerkoenigUnavailableError(f"HTTP-Fehler beim Aufruf der Tankerkönig-API: {exc}") from exc

    @staticmethod
    def _normalize_station(raw: dict) -> dict:
        """Bildet ein rohes Tankerkönig-Stations-Dict auf unser
        app.models.Station-Schema ab. Feldnamen inzwischen live gegen die
        echte API verifiziert (siehe Modul-Docstring, Episode 10)."""
        street = raw.get("street", "")
        house_number = raw.get("houseNumber", "")
        full_street = f"{street} {house_number}".strip()
        return {
            "uuid": raw["id"],
            "name": raw.get("name", "unbekannt"),
            "brand": raw.get("brand", "unbekannt"),
            "street": full_street or "unbekannt",
            "place": raw.get("place", "unbekannt"),
            "post_code": str(raw.get("postCode", "")),
            "latitude": float(raw.get("lat", 0.0)),
            "longitude": float(raw.get("lng", 0.0)),
        }
