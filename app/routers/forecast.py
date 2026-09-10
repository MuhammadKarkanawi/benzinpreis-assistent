from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app import forecasting
from app.config import Settings, get_settings
from app.data_loader import load_price_series
from app.db import get_session
from app.models import ForecastResult
from app.schemas import ForecastOut

router = APIRouter(prefix="/forecast", tags=["Vorhersage"])


@router.get("/{station_uuid}", response_model=ForecastOut)
def get_forecast(
    station_uuid: str,
    fuel_type: Literal["e5", "e10", "diesel"] = "e5",
    horizon_hours: int = Query(default=24, ge=1, le=72),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    df = load_price_series(session, station_uuid, fuel_type)
    if df.empty:
        raise HTTPException(status_code=404, detail="Keine Preisdaten für diese Tankstelle/Kraftstoffsorte gefunden.")

    try:
        point = forecasting.forecast(
            df, fuel_type, horizon_hours=horizon_hours, min_history_days=settings.min_history_days_for_forecast
        )
        window = forecasting.best_refuel_window(df, fuel_type, horizon_hours=48)
    except forecasting.InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    current_price = float(df.sort_values("timestamp")[fuel_type].iloc[-1])

    result = ForecastResult(
        station_uuid=station_uuid,
        fuel_type=fuel_type,
        horizon_hours=horizon_hours,
        predicted_price=point.predicted_price,
        predicted_direction=point.direction,
        confidence=point.confidence,
        method=point.method,
        best_refuel_window_start=window.start,
        best_refuel_window_end=window.end,
    )
    session.add(result)
    session.commit()

    return ForecastOut(
        station_uuid=station_uuid,
        fuel_type=fuel_type,
        horizon_hours=horizon_hours,
        current_price=current_price,
        predicted_price=point.predicted_price,
        predicted_direction=point.direction,
        confidence=point.confidence,
        method=point.method,
        best_refuel_window_start=window.start,
        best_refuel_window_end=window.end,
        generated_at=datetime.now(timezone.utc),
    )
