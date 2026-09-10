"""Laden der Beispieldaten (oder echter Tankerkönig-Daten im selben Schema)
aus CSV-Dateien in die Datenbank, sowie Hilfsfunktionen zum Auslesen einer
Preiszeitreihe für die Forecasting-Logik."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlmodel import Session, select

from app.models import PriceRecord, Station


def seed_from_csv(session: Session, data_dir: Path, force: bool = False) -> dict:
    """Lädt data/stations.csv und data/prices.csv in die Datenbank, sofern
    noch keine Stationen vorhanden sind (oder force=True)."""
    existing = session.exec(select(Station)).first()
    if existing is not None and not force:
        return {"skipped": True, "reason": "Datenbank bereits befüllt"}

    stations_path = data_dir / "stations.csv"
    prices_path = data_dir / "prices.csv"
    if not stations_path.exists() or not prices_path.exists():
        raise FileNotFoundError(
            f"Beispieldaten fehlen ({stations_path}, {prices_path}). "
            "Erst 'python -m scripts.generate_sample_data' ausführen."
        )

    n_stations = 0
    with stations_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            session.add(
                Station(
                    uuid=row["uuid"],
                    name=row["name"],
                    brand=row["brand"],
                    street=row["street"],
                    place=row["place"],
                    post_code=row["post_code"],
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                )
            )
            n_stations += 1
    session.commit()

    n_prices = 0
    with prices_path.open(newline="", encoding="utf-8") as f:
        batch = []
        for row in csv.DictReader(f):
            batch.append(
                PriceRecord(
                    station_uuid=row["station_uuid"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    e5=float(row["e5"]) if row["e5"] else None,
                    e10=float(row["e10"]) if row["e10"] else None,
                    diesel=float(row["diesel"]) if row["diesel"] else None,
                    e5_change=int(row["e5_change"]),
                    e10_change=int(row["e10_change"]),
                    diesel_change=int(row["diesel_change"]),
                )
            )
            n_prices += 1
            if len(batch) >= 1000:
                session.add_all(batch)
                session.commit()
                batch = []
        if batch:
            session.add_all(batch)
            session.commit()

    return {"skipped": False, "n_stations": n_stations, "n_prices": n_prices}


def load_price_series(session: Session, station_uuid: str, fuel_type: str) -> pd.DataFrame:
    """Liest die Preiszeitreihe einer Station/Kraftstoffsorte als DataFrame
    mit Spalten ['timestamp', fuel_type], sortiert nach Zeit."""
    if fuel_type not in ("e5", "e10", "diesel"):
        raise ValueError(f"Unbekannte Kraftstoffsorte: {fuel_type}")

    statement = (
        select(PriceRecord.timestamp, getattr(PriceRecord, fuel_type))
        .where(PriceRecord.station_uuid == station_uuid)
        .order_by(PriceRecord.timestamp)
    )
    rows = session.exec(statement).all()
    df = pd.DataFrame(rows, columns=["timestamp", fuel_type])
    df = df.dropna().reset_index(drop=True)
    return df
