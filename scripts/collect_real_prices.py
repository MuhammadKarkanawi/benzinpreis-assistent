"""
Wiederkehrender Sammel-Job: ruft die aktuellen Preise der in
TANKERKOENIG_STATION_UUIDS konfigurierten echten Tankstellen ab und speichert
sie als neuen PriceRecord in der Datenbank - dieselbe Tabelle, die auch die
synthetischen Beispieldaten nutzt (siehe app/models.py), sodass Forecasting/
Grounding ohne Codeänderung auch mit echten, wachsenden Daten funktionieren.

Absichtlich als eigenständiges, wiederholt aufrufbares Skript (kein
Hintergrund-Task in der FastAPI-App selbst), damit es unabhängig von der
laufenden Anwendung über einen simplen, plattformüblichen Scheduler
ausgeführt werden kann (siehe README, Abschnitt "Echte Daten sammeln"):

    macOS (launchd) oder einfacher per cron, z.B. stündlich:
        0 * * * *  cd /pfad/zum/projekt && .venv/bin/python -m scripts.collect_real_prices

Voraussetzung: TANKERKOENIG_API_KEY und TANKERKOENIG_STATION_UUIDS in .env
(siehe scripts/discover_real_stations.py für Letzteres). Fehlt eine der
beiden Einstellungen, beendet sich das Skript ohne Fehler (Exit-Code 0) mit
einer klaren Meldung - so kann es bereits in einen Scheduler eingetragen
werden, bevor die Tankerkönig-Registrierung abgeschlossen ist, ohne
Fehler-Alarme auszulösen.

Status: Inzwischen erfolgreich gegen die echte Tankerkönig-API verifiziert
(siehe AI_DEVELOPMENT_LOG.md, Episode 10) - u.a. dabei gefunden und behoben:
ein zu knapper API-Timeout und Stationen, die trotz Status ungleich
"no prices" keine verwertbaren Preise liefern (z.B. vorübergehend
geschlossen).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine, init_db
from app.integrations.tankerkoenig_client import TankerkoenigError, TankerkoenigClient
from app.models import PriceRecord

FUEL_TYPES = ("e5", "e10", "diesel")


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _latest_prices(session: Session, station_uuid: str) -> dict[str, float | None]:
    latest = session.exec(
        select(PriceRecord)
        .where(PriceRecord.station_uuid == station_uuid)
        .order_by(PriceRecord.timestamp.desc())
        .limit(1)
    ).first()
    if latest is None:
        return {ft: None for ft in FUEL_TYPES}
    return {ft: getattr(latest, ft) for ft in FUEL_TYPES}


def collect() -> dict:
    settings = get_settings()
    if not settings.tankerkoenig_api_key:
        print("TANKERKOENIG_API_KEY nicht gesetzt - Sammel-Lauf übersprungen (kein Fehler).")
        return {"skipped": True, "reason": "kein API-Key"}

    station_uuids = [u.strip() for u in settings.tankerkoenig_station_uuids.split(",") if u.strip()]
    if not station_uuids:
        print(
            "TANKERKOENIG_STATION_UUIDS nicht gesetzt - Sammel-Lauf übersprungen. "
            "Erst 'python -m scripts.discover_real_stations' ausführen."
        )
        return {"skipped": True, "reason": "keine Stationen konfiguriert"}

    client = TankerkoenigClient(
        api_key=settings.tankerkoenig_api_key, timeout=settings.tankerkoenig_timeout_seconds
    )
    init_db()

    all_prices: dict[str, dict] = {}
    try:
        for batch in _chunk(station_uuids, 10):  # prices.php erlaubt max. 10 IDs pro Aufruf
            all_prices.update(client.current_prices(batch))
    except TankerkoenigError as exc:
        print(f"Fehler beim Abruf der Tankerkönig-API: {exc}", file=sys.stderr)
        return {"skipped": True, "reason": f"API-Fehler: {exc}"}

    now = datetime.now(timezone.utc)
    n_inserted = 0
    with Session(engine) as session:
        for station_uuid in station_uuids:
            raw = all_prices.get(station_uuid)
            new_values = {ft: raw.get(ft) for ft in FUEL_TYPES} if raw is not None else {ft: None for ft in FUEL_TYPES}
            # Nicht nur auf status == "no prices" prüfen: die echte API liefert
            # auch mit einem anderen Status (z.B. vorübergehend geschlossene
            # Station) manchmal keinen einzigen verwertbaren Preis - das war
            # beim ersten echten Sammel-Lauf tatsächlich der Fall (siehe
            # AI_DEVELOPMENT_LOG.md, Episode 10). In diesem Fall ebenfalls
            # überspringen, statt einen Datensatz aus lauter Nullwerten zu
            # speichern.
            if raw is None or raw.get("status") == "no prices" or all(v is None for v in new_values.values()):
                print(f"  {station_uuid}: keine Preisdaten in der Antwort, übersprungen.")
                continue

            previous = _latest_prices(session, station_uuid)
            changes = {
                f"{ft}_change": int(new_values[ft] is not None and new_values[ft] != previous[ft])
                for ft in FUEL_TYPES
            }

            session.add(
                PriceRecord(
                    station_uuid=station_uuid,
                    timestamp=now,
                    e5=new_values["e5"],
                    e10=new_values["e10"],
                    diesel=new_values["diesel"],
                    **changes,
                )
            )
            n_inserted += 1
            print(f"  {station_uuid}: e5={new_values['e5']} e10={new_values['e10']} diesel={new_values['diesel']}")
        session.commit()

    print(f"{n_inserted} Preis-Datensatz/-sätze gespeichert ({now.isoformat()}).")
    return {"skipped": False, "n_inserted": n_inserted, "timestamp": now.isoformat()}


if __name__ == "__main__":
    collect()
