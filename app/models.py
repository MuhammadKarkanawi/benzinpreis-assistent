"""
Persistente Datenmodelle (SQLModel = SQLAlchemy + Pydantic).

Tabellen:
- Station: Stammdaten einer Tankstelle.
- PriceRecord: einzelne Preis-Beobachtung/-Änderung einer Tankstelle (Zeitreihe).
- ForecastResult: gespeichertes Ergebnis einer berechneten Vorhersage (nicht-KI).
- QueryLog: jede an die KI-Komponente gestellte Frage inkl. Antwort, verwendetem
  Kontext und Metadaten - dient sowohl der Nachvollziehbarkeit als auch der
  späteren Auswertung/Evaluation.
"""
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Station(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(index=True, unique=True)
    name: str
    brand: str
    street: str
    place: str
    post_code: str
    latitude: float
    longitude: float


class PriceRecord(SQLModel, table=True):
    """Eine Preisbeobachtung. Entspricht (grob) dem Schema der öffentlichen
    Tankerkönig/MTS-K Preishistorie, damit reale Daten später ohne
    Code-Änderung eingespielt werden können."""

    id: Optional[int] = Field(default=None, primary_key=True)
    station_uuid: str = Field(index=True, foreign_key="station.uuid")
    timestamp: datetime = Field(index=True)
    diesel: Optional[float] = None
    e5: Optional[float] = None
    e10: Optional[float] = None
    diesel_change: int = 0  # 0 = keine Änderung, 1 = Preisänderung in diesem Datensatz
    e5_change: int = 0
    e10_change: int = 0


class ForecastResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    station_uuid: str = Field(index=True)
    fuel_type: str  # "e5" | "e10" | "diesel"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    horizon_hours: int
    predicted_price: float
    predicted_direction: str  # "steigend" | "fallend" | "stabil"
    confidence: float  # 0..1, heuristisch (siehe forecasting.py) - KEINE kalibrierte Wahrscheinlichkeit
    method: str  # z.B. "weighted_moving_average+seasonal"
    best_refuel_window_start: Optional[datetime] = None
    best_refuel_window_end: Optional[datetime] = None


class QueryLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    station_uuid: str
    question: str
    grounding_facts_json: str
    answer: Optional[str] = None
    used_context: bool = True  # False, wenn im Vergleichsmodus ohne Kontext getestet
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    flagged_ungrounded: bool = False  # von der Validierung als evtl. erfunden markiert
