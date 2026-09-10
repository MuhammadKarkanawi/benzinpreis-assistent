"""API Request/Response-Schemas (Pydantic), getrennt von den DB-Modellen."""
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


class StationOut(BaseModel):
    uuid: str
    name: str
    brand: str
    street: str
    place: str
    post_code: str
    latitude: float
    longitude: float


class PricePoint(BaseModel):
    timestamp: datetime
    price: float


class PriceHistoryOut(BaseModel):
    station_uuid: str
    fuel_type: str
    points: list[PricePoint]


class ForecastOut(BaseModel):
    station_uuid: str
    fuel_type: str
    horizon_hours: int
    current_price: Optional[float]
    predicted_price: float
    predicted_direction: Literal["steigend", "fallend", "stabil"]
    confidence: float = Field(..., ge=0.0, le=1.0, description="Heuristischer Score, keine kalibrierte Wahrscheinlichkeit")
    method: str
    best_refuel_window_start: Optional[datetime]
    best_refuel_window_end: Optional[datetime]
    generated_at: datetime


class AskRequest(BaseModel):
    station_uuid: str
    fuel_type: Literal["e5", "e10", "diesel"] = "e5"
    question: str
    use_context: bool = True  # False = Vergleichs-/Baseline-Modus ohne gestützten Kontext


class AskResponse(BaseModel):
    answer: str
    used_context: bool
    grounding_facts: dict
    flagged_ungrounded: bool
    latency_ms: float
    model: str
    error: Optional[str] = None


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    ai_backend_reachable: Optional[bool]
    ai_base_url: str
    ai_model: str
    version: str = "0.1.0"
