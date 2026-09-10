"""
Erzeugt reproduzierbare synthetische Beispieldaten im Format der öffentlichen
Tankerkönig/MTS-K Preishistorie (https://github.com/tankerkoenig/tankerkoenig-data).

Warum synthetisch statt echter Daten?
Der Cloud-Entwicklungs-Workspace, in dem dieses Projekt entstanden ist, hatte
keinen Netzwerkzugriff auf GitHub-Rohdaten. Die Daten wurden daher mit einem
festen Zufalls-Seed generiert, folgen aber realistischen, dokumentierten
Mustern (Tagesverlauf, Wochentags-Muster, langsamer Trend, Rauschen), damit
die Vorhersage- und Empfehlungslogik sinnvoll getestet werden kann.

Möchte man echte Daten verwenden: Datei(en) im selben Schema
(stations.csv, prices.csv) von https://github.com/tankerkoenig/tankerkoenig-data
herunterladen und in data/ ablegen - der Loader (app/data_loader.py) liest
dieses Format unverändert ein.

Ausführen mit:  python -m scripts.generate_sample_data
"""
from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

RNG_SEED = 42
N_DAYS = 120
CHANGE_INTERVAL_MIN_HOURS = 2
CHANGE_INTERVAL_MAX_HOURS = 4

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

STATIONS = [
    {
        "uuid": "51d4b6c8-a1e1-4c9b-8f2a-000000000001",
        "name": "Freie Tankstelle Dortmund-Mitte",
        "brand": "freie Tankstelle",
        "street": "Kampstraße 12",
        "place": "Dortmund",
        "post_code": "44137",
        "latitude": 51.5136,
        "longitude": 7.4653,
        "base_price": 1.739,
        "trend_eur_per_day": 0.0009,  # langsamer Aufwärtstrend
    },
    {
        "uuid": "51d4b6c8-a1e1-4c9b-8f2a-000000000002",
        "name": "Markentankstelle Dortmund-Hörde",
        "brand": "Marke A",
        "street": "Faßstraße 40",
        "place": "Dortmund",
        "post_code": "44225",
        "latitude": 51.4794,
        "longitude": 7.4919,
        "base_price": 1.789,
        "trend_eur_per_day": 0.0004,
    },
    {
        "uuid": "51d4b6c8-a1e1-4c9b-8f2a-000000000003",
        "name": "Autohof Dortmund-Ost",
        "brand": "Marke B",
        "street": "B1 Ausfahrt Ost",
        "place": "Dortmund",
        "post_code": "44149",
        "latitude": 51.5153,
        "longitude": 7.5502,
        "base_price": 1.719,
        "trend_eur_per_day": -0.0002,  # leicht fallend
    },
]

FUELS = ["e5", "e10", "diesel"]
# realistischer Aufschlag/Abschlag je Kraftstoffsorte relativ zu e5
FUEL_OFFSET = {"e5": 0.0, "e10": -0.075, "diesel": -0.02}


def daily_seasonal_factor(hour: int) -> float:
    """Typisches deutsches Tagesmuster: morgens teurer (Peak ~8-9 Uhr),
    zum Abend hin günstiger (Tiefpunkt ~19-21 Uhr)."""
    # Kosinus-Kurve mit Peak bei Stunde 8
    return 0.035 * math.cos((hour - 8) / 24.0 * 2 * math.pi)


def weekday_seasonal_factor(weekday: int) -> float:
    """0=Montag .. 6=Sonntag. In DE häufig: Di/Mi tendenziell günstiger,
    Wochenende teurer."""
    factors = {0: 0.005, 1: -0.01, 2: -0.012, 3: -0.004, 4: 0.008, 5: 0.015, 6: 0.018}
    return factors.get(weekday, 0.0)


def generate_station_series(rng: random.Random, station: dict, start: datetime, n_days: int):
    rows = []
    current = start
    end = start + timedelta(days=n_days)

    # Random Walk Komponente (z.B. Rohölpreis-Schwankungen), pro Kraftstoff leicht korreliert
    walk = 0.0
    last_price = {f: None for f in FUELS}

    t = current
    day_index = 0
    while t < end:
        day_index = (t - start).days
        walk += rng.gauss(0, 0.0025)
        walk = max(-0.15, min(0.15, walk))  # begrenzen, damit Preis plausibel bleibt

        # gelegentlicher "Preisschock" (z.B. Rohölpreis-Sprung), ~ alle 30 Tage
        shock = 0.0
        if rng.random() < 1 / (30 * 12):  # Wahrscheinlichkeit pro ~2h-Schritt
            shock = rng.choice([-1, 1]) * rng.uniform(0.03, 0.07)
            walk += shock

        trend = station["trend_eur_per_day"] * day_index
        seasonal = daily_seasonal_factor(t.hour) + weekday_seasonal_factor(t.weekday())
        noise = rng.gauss(0, 0.004)

        base = station["base_price"] + trend + seasonal + walk + noise

        e5_price = round(base + FUEL_OFFSET["e5"], 3)
        e10_price = round(base + FUEL_OFFSET["e10"], 3)
        diesel_price = round(base + FUEL_OFFSET["diesel"] + rng.gauss(0, 0.003), 3)

        prices = {"e5": e5_price, "e10": e10_price, "diesel": diesel_price}
        changes = {}
        for f in FUELS:
            prev = last_price[f]
            changes[f] = 1 if (prev is None or abs(prev - prices[f]) >= 0.001) else 0
            last_price[f] = prices[f]

        rows.append(
            {
                "station_uuid": station["uuid"],
                "timestamp": t.replace(microsecond=0).isoformat(),
                "e5": e5_price,
                "e10": e10_price,
                "diesel": diesel_price,
                "e5_change": changes["e5"],
                "e10_change": changes["e10"],
                "diesel_change": changes["diesel"],
            }
        )

        step_hours = rng.uniform(CHANGE_INTERVAL_MIN_HOURS, CHANGE_INTERVAL_MAX_HOURS)
        t = t + timedelta(hours=step_hours)

    return rows


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(RNG_SEED)

    start = datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(days=N_DAYS)

    # stations.csv
    stations_path = DATA_DIR / "stations.csv"
    with stations_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["uuid", "name", "brand", "street", "place", "post_code", "latitude", "longitude"],
        )
        writer.writeheader()
        for s in STATIONS:
            writer.writerow({k: s[k] for k in writer.fieldnames})

    # prices.csv
    prices_path = DATA_DIR / "prices.csv"
    all_rows = []
    for station in STATIONS:
        all_rows.extend(generate_station_series(rng, station, start, N_DAYS))
    all_rows.sort(key=lambda r: (r["station_uuid"], r["timestamp"]))

    with prices_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "station_uuid",
                "timestamp",
                "e5",
                "e10",
                "diesel",
                "e5_change",
                "e10_change",
                "diesel_change",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Geschrieben: {stations_path} ({len(STATIONS)} Stationen)")
    print(f"Geschrieben: {prices_path} ({len(all_rows)} Preisdatensätze, {N_DAYS} Tage)")


if __name__ == "__main__":
    main()
