"""
Einmaliges Setup-Skript: sucht echte Tankstellen im Umkreis eines Ortes über
die Tankerkönig-API und zeigt sie an. Mit `--write` werden die ausgewählten
Stationen zusätzlich in die Datenbank übernommen und ihre UUIDs in `.env`
eingetragen (TANKERKOENIG_STATION_UUIDS), damit
`scripts/collect_real_prices.py` sie danach findet.

Voraussetzung: TANKERKOENIG_API_KEY in der `.env` (siehe .env.example) -
Registrierung unter https://onboarding.tankerkoenig.de. War zum Zeitpunkt
der Entwicklung wegen Wartungsarbeiten des Anbieters nicht möglich, siehe
AI_DEVELOPMENT_LOG.md Episode 9 - dieses Skript ist deshalb NICHT gegen die
echte API verifiziert.

Verwendung:
    python -m scripts.discover_real_stations --lat 51.5136 --lng 7.4653 --radius 5
    python -m scripts.discover_real_stations --lat 51.5136 --lng 7.4653 --radius 5 \
        --pick real-uuid-1,real-uuid-2,real-uuid-3 --write
"""
from __future__ import annotations

import argparse
import sys

from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine, init_db
from app.integrations.tankerkoenig_client import TankerkoenigClient, TankerkoenigError
from app.models import Station


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=51.5136, help="Breitengrad (Standard: Dortmund-Mitte)")
    parser.add_argument("--lng", type=float, default=7.4653, help="Längengrad (Standard: Dortmund-Mitte)")
    parser.add_argument("--radius", type=float, default=5.0, help="Suchradius in km (max. 25)")
    parser.add_argument(
        "--pick",
        type=str,
        default="",
        help="Komma-getrennte Liste von UUIDs aus der Trefferliste, die übernommen werden sollen",
    )
    parser.add_argument(
        "--write", action="store_true", help="Ausgewählte Stationen wirklich in DB/.env übernehmen (sonst nur Anzeige)"
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.tankerkoenig_api_key:
        print(
            "TANKERKOENIG_API_KEY ist nicht gesetzt (.env). Registrierung unter "
            "https://onboarding.tankerkoenig.de - siehe AI_DEVELOPMENT_LOG.md Episode 9.",
            file=sys.stderr,
        )
        return 1

    client = TankerkoenigClient(api_key=settings.tankerkoenig_api_key)
    try:
        stations = client.find_stations_nearby(args.lat, args.lng, radius_km=args.radius)
    except TankerkoenigError as exc:
        print(f"Fehler beim Abruf: {exc}", file=sys.stderr)
        return 1

    if not stations:
        print("Keine Tankstellen im angegebenen Umkreis gefunden.")
        return 0

    print(f"{len(stations)} Tankstelle(n) gefunden:\n")
    for s in stations:
        print(f"  {s['uuid']}  {s['name']} ({s['brand']}) - {s['street']}, {s['post_code']} {s['place']}")

    picked = [u.strip() for u in args.pick.split(",") if u.strip()]
    if not picked:
        print("\nKeine Auswahl übergeben (--pick) - nur Anzeige, nichts gespeichert.")
        return 0

    selected = [s for s in stations if s["uuid"] in picked]
    missing = set(picked) - {s["uuid"] for s in selected}
    if missing:
        print(f"\nWarnung: folgende UUIDs waren nicht in der Trefferliste: {missing}", file=sys.stderr)

    if not args.write:
        print(f"\n{len(selected)} Station(en) ausgewählt - Probelauf, nichts gespeichert (--write fehlt).")
        return 0

    init_db()
    with Session(engine) as session:
        for s in selected:
            existing = session.exec(select(Station).where(Station.uuid == s["uuid"])).first()
            if existing:
                print(f"  {s['uuid']} existiert bereits in der DB, übersprungen.")
                continue
            session.add(Station(**s))
        session.commit()

    print(f"\n{len(selected)} echte Station(en) in die Datenbank übernommen.")
    print(
        "Bitte jetzt manuell in .env eintragen (oder ergänzen, komma-getrennt):\n"
        f"  TANKERKOENIG_STATION_UUIDS={','.join(s['uuid'] for s in selected)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
