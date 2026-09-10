from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.data_loader import load_price_series
from app.db import get_session
from app.schemas import PriceHistoryOut, PricePoint

router = APIRouter(prefix="/prices", tags=["Preisverlauf"])


@router.get("/{station_uuid}", response_model=PriceHistoryOut)
def get_price_history(
    station_uuid: str,
    fuel_type: Literal["e5", "e10", "diesel"] = "e5",
    days: int = Query(default=14, ge=1, le=120, description="Wie viele Tage Historie zurück"),
    session: Session = Depends(get_session),
):
    df = load_price_series(session, station_uuid, fuel_type)
    if df.empty:
        raise HTTPException(status_code=404, detail="Keine Preisdaten für diese Tankstelle/Kraftstoffsorte gefunden.")

    cutoff = df["timestamp"].max() - timedelta(days=days)
    df = df[df["timestamp"] >= cutoff]

    points = [PricePoint(timestamp=row.timestamp, price=float(getattr(row, fuel_type))) for row in df.itertuples()]
    return PriceHistoryOut(station_uuid=station_uuid, fuel_type=fuel_type, points=points)
