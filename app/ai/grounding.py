"""Sammelt die 'Fakten', auf die die KI-Antwort gestützt werden muss.

Alle Werte hier stammen ausschließlich aus der deterministischen
Forecasting-Logik (app/forecasting.py) bzw. direkt aus der Datenbank -
niemals aus einem Sprachmodell. Das ist die Grundlage des RAG-artigen
"grounding" der Antworten.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from app import forecasting
from app.config import Settings
from app.data_loader import load_price_series
from app.models import Station
from sqlmodel import select


class NoDataForStationError(Exception):
    pass


def gather_facts(session: Session, settings: Settings, station_uuid: str, fuel_type: str) -> dict:
    station = session.get(Station, None) if False else session.exec(
        select(Station).where(Station.uuid == station_uuid)
    ).first()
    if station is None:
        raise NoDataForStationError(f"Unbekannte Tankstelle: {station_uuid}")

    df = load_price_series(session, station_uuid, fuel_type)
    if df.empty:
        raise NoDataForStationError(f"Keine Preisdaten für Tankstelle {station_uuid} ({fuel_type}) vorhanden.")

    current_price = float(df.sort_values("timestamp")[fuel_type].iloc[-1])
    current_ts = df["timestamp"].max()

    facts: dict = {
        "station_name": station.name,
        "station_place": station.place,
        "fuel_type": fuel_type,
        "current_price_eur": round(current_price, 3),
        "current_price_timestamp": str(current_ts),
        "data_period_days": int((df["timestamp"].max() - df["timestamp"].min()).days),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Aktuelle Preise der jeweils ANDEREN Kraftstoffsorten mitgeben, damit
    # Vergleichsfragen ("ist E10 gerade günstiger als Diesel?") beantwortbar
    # sind, ohne erfunden zu werden. Vorhersage/Tankzeit-Empfehlung beziehen
    # sich weiterhin ausschließlich auf `fuel_type`.
    other_prices: dict[str, float] = {}
    for other_fuel in ("e5", "e10", "diesel"):
        if other_fuel == fuel_type:
            continue
        try:
            other_df = load_price_series(session, station_uuid, other_fuel)
            if not other_df.empty:
                other_prices[other_fuel] = round(
                    float(other_df.sort_values("timestamp")[other_fuel].iloc[-1]), 3
                )
        except Exception:
            continue
    if other_prices:
        facts["other_current_prices_eur"] = other_prices

    try:
        trend = forecasting.compute_trend_per_day(df, fuel_type)
        facts["trend_eur_per_day"] = round(trend, 4)
    except forecasting.InsufficientDataError:
        facts["trend_eur_per_day"] = None

    try:
        fc = forecasting.forecast(df, fuel_type, horizon_hours=settings.forecast_horizon_hours)
        facts["forecast"] = {
            "horizon_hours": settings.forecast_horizon_hours,
            "predicted_price_eur": fc.predicted_price,
            "direction": fc.direction,
            "confidence_heuristic_0_to_1": fc.confidence,
            "method": fc.method,
        }
    except forecasting.InsufficientDataError as exc:
        facts["forecast"] = None
        facts["forecast_unavailable_reason"] = str(exc)

    try:
        window = forecasting.best_refuel_window(df, fuel_type, horizon_hours=48)
        facts["best_refuel_window"] = {
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "expected_price_eur": window.expected_price,
            "expected_savings_vs_now_eur": window.expected_savings_vs_now,
        }
    except forecasting.InsufficientDataError:
        facts["best_refuel_window"] = None

    return facts
