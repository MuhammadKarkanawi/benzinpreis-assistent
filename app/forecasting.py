"""
Nicht-KI-Kernlogik: Zeitreihenanalyse und Kurzfrist-Vorhersage von Kraftstoffpreisen.

Diese Datei enthält bewusst KEINE Aufrufe eines Sprachmodells. Die gesamte
Vorhersage- und Empfehlungslogik ist deterministisch/statistisch (gleitende
Durchschnitte, Wochentags-/Tageszeit-Saisonalität, linearer Trend) und damit
vollständig deterministisch testbar.

Methodik (bewusst einfach gehalten, aber nachvollziehbar und begründbar):

1. Saisonales Profil: mittlere Abweichung des Preises vom Gesamtmittel je
   (Wochentag, Stunde) - erfasst z.B. "abends günstiger", "Dienstags günstiger".
2. Trend: lineare Regression auf die Tagesmittelwerte der letzten N Tage -
   erfasst langsame Auf-/Abwärtsbewegungen (z.B. Rohölpreis-Entwicklung).
3. Vorhersage = letzter beobachteter Preis
                + Trendanteil bis zum Zielzeitpunkt
                + (saisonale Abweichung zum Zielzeitpunkt - saisonale
                   Abweichung zum aktuellen Zeitpunkt)
4. Konfidenz: heuristischer Score basierend auf (a) Menge der verfügbaren
   Historie und (b) Streuung der Preise im relevanten (Wochentag, Stunde)-
   Bucket. Dies ist AUSDRÜCKLICH keine kalibrierte Wahrscheinlichkeit,
   sondern ein Vertrauens-Heuristikwert in [0, 1] (siehe Anforderung
   "Konfidenz darf nicht als Wahrscheinlichkeit dargestellt werden, außer
   sie wurde entsprechend begründet/kalibriert").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Optional

import numpy as np
import pandas as pd

DIRECTION = Literal["steigend", "fallend", "stabil"]

# Schwelle (in Euro), unterhalb derer eine Vorhersage als "stabil" gilt.
# 0.5 Cent liegt deutlich unterhalb der üblichen kleinsten Preisschritte an
# deutschen Tankstellen (meist 1-2 Cent) und dient nur dazu, Rauschen von
# einer tatsächlich gerichteten Bewegung zu unterscheiden.
STABLE_THRESHOLD_EUR = 0.005

# Plausibilitätsgrenzen für Kraftstoffpreise in Euro/Liter (Datenqualität).
MIN_PLAUSIBLE_PRICE = 0.80
MAX_PLAUSIBLE_PRICE = 3.50


class InsufficientDataError(Exception):
    """Wird ausgelöst, wenn zu wenig valide Historie für eine Vorhersage vorliegt."""


@dataclass
class SeasonalProfile:
    overall_mean: float
    by_weekday_hour: dict[tuple[int, int], float]  # (weekday, hour) -> mittlere Abweichung
    n_days: int


@dataclass
class ForecastPoint:
    predicted_price: float
    direction: DIRECTION
    confidence: float
    method: str


@dataclass
class RefuelWindow:
    start: datetime
    end: datetime
    expected_price: float
    expected_savings_vs_now: float


def validate_and_clean(df: pd.DataFrame, price_col: str) -> pd.DataFrame:
    """Entfernt/markiert unplausible Preiswerte (Datenqualitätsprüfung).

    Erwartet einen DataFrame mit Spalten ['timestamp', price_col], sortiert
    nach timestamp. Gibt einen bereinigten DataFrame zurück.
    """
    if df.empty:
        return df
    clean = df.copy()
    mask_valid = clean[price_col].between(MIN_PLAUSIBLE_PRICE, MAX_PLAUSIBLE_PRICE)
    dropped = (~mask_valid).sum()
    clean = clean.loc[mask_valid].reset_index(drop=True)
    clean.attrs["n_dropped_implausible"] = int(dropped)
    return clean


def _resample_hourly(df: pd.DataFrame, price_col: str) -> pd.DataFrame:
    """Bringt unregelmäßige Preisänderungs-Zeitpunkte auf ein stündliches
    Raster (letzter bekannter Preis gilt bis zur nächsten Änderung - "forward
    fill"), damit Saisonalität pro Stunde sauber berechnet werden kann."""
    ts = pd.to_datetime(df["timestamp"])
    s = pd.Series(df[price_col].to_numpy(), index=pd.DatetimeIndex(ts)).sort_index()
    hourly = s.resample("1h").ffill().dropna()
    return hourly.to_frame(name=price_col)


def compute_seasonal_profile(df: pd.DataFrame, price_col: str) -> SeasonalProfile:
    """Berechnet die mittlere Abweichung je (Wochentag, Stunde).

    Wichtig: Die Abweichung wird NICHT gegen den globalen Mittelwert gebildet,
    sondern gegen einen gleitenden 7-Tage-Mittelwert je Zeitpunkt ("trend
    baseline"). Andernfalls würde ein starker langfristiger Preistrend
    fälschlich als saisonaler Effekt interpretiert ("Trend-Leakage") und
    könnte - insbesondere bei kurzer Historie - sogar das Vorzeichen der
    Vorhersage verfälschen. Ein 7-Tage-Fenster ist lang genug, um Trend zu
    glätten, aber kurz genug, um echte Wochentags-Effekte (z.B. "dienstags
    günstiger") nicht mit herauszumitteln.
    """
    hourly = _resample_hourly(df, price_col)
    if hourly.empty:
        raise InsufficientDataError("Keine validen Preisdaten für saisonales Profil vorhanden.")
    overall_mean = float(hourly[price_col].mean())

    hourly = hourly.copy()
    window = min(24 * 7, max(24, len(hourly) // 2 * 2 or 24))
    trend_baseline = hourly[price_col].rolling(window=window, center=True, min_periods=24).mean()
    hourly["deviation"] = hourly[price_col] - trend_baseline
    hourly = hourly.dropna(subset=["deviation"])

    if hourly.empty:
        # zu wenig Historie für ein sinnvolles Trend-Fenster -> auf einfache
        # Abweichung vom Gesamtmittel zurückfallen
        hourly = _resample_hourly(df, price_col).copy()
        hourly["deviation"] = hourly[price_col] - overall_mean

    hourly["weekday"] = hourly.index.weekday
    hourly["hour"] = hourly.index.hour
    grouped = hourly.groupby(["weekday", "hour"])["deviation"].mean()
    by_weekday_hour = {idx: float(val) for idx, val in grouped.items()}
    n_days = int((_resample_hourly(df, price_col).index.max() - _resample_hourly(df, price_col).index.min()).days) + 1
    return SeasonalProfile(overall_mean=overall_mean, by_weekday_hour=by_weekday_hour, n_days=n_days)


def compute_trend_per_day(df: pd.DataFrame, price_col: str, lookback_days: int = 14) -> float:
    """Lineare Regression der Tagesmittelwerte der letzten `lookback_days`
    Tage. Rückgabe: geschätzte Preisänderung in Euro pro Tag."""
    hourly = _resample_hourly(df, price_col)
    if hourly.empty:
        return 0.0
    daily = hourly[price_col].resample("1D").mean().dropna()
    daily = daily.tail(lookback_days)
    if len(daily) < 2:
        return 0.0
    x = np.arange(len(daily), dtype=float)
    y = daily.to_numpy(dtype=float)
    slope, _intercept = np.polyfit(x, y, 1)
    return float(slope)


def _seasonal_deviation(profile: SeasonalProfile, ts: datetime) -> float:
    return profile.by_weekday_hour.get((ts.weekday(), ts.hour), 0.0)


def _bucket_std(df: pd.DataFrame, price_col: str, weekday: int, hour: int) -> Optional[float]:
    hourly = _resample_hourly(df, price_col)
    if hourly.empty:
        return None
    hourly = hourly.copy()
    hourly["weekday"] = hourly.index.weekday
    hourly["hour"] = hourly.index.hour
    bucket = hourly[(hourly["weekday"] == weekday) & (hourly["hour"] == hour)][price_col]
    if len(bucket) < 2:
        return None
    return float(bucket.std())


def heuristic_confidence(n_days_history: int, bucket_std: Optional[float], min_history_days: int) -> float:
    """Heuristischer Konfidenz-Score in [0, 1]. KEINE kalibrierte Wahrscheinlichkeit.

    - Mehr Historie -> höhere Konfidenz (sättigt bei ~4x min_history_days).
    - Höhere Streuung im relevanten Zeit-Bucket -> niedrigere Konfidenz.
    """
    history_factor = min(1.0, n_days_history / max(1, 4 * min_history_days))
    if bucket_std is None:
        spread_factor = 0.5  # unbekannte Streuung -> mittlere Unsicherheit
    else:
        # 0.10 EUR Streuung -> spread_factor ~= 0.37; sättigt bei sehr geringer Streuung nahe 1.0
        spread_factor = float(np.exp(-bucket_std / 0.05))
    score = 0.5 * history_factor + 0.5 * spread_factor
    return round(float(np.clip(score, 0.0, 1.0)), 3)


def forecast(
    df: pd.DataFrame,
    price_col: str,
    horizon_hours: int,
    now: Optional[datetime] = None,
    min_history_days: int = 7,
) -> ForecastPoint:
    """Berechnet eine Kurzfrist-Preisvorhersage für `horizon_hours` in die Zukunft."""
    clean = validate_and_clean(df, price_col)
    if clean.empty:
        raise InsufficientDataError("Keine validen Preisdaten vorhanden.")

    now = now or clean["timestamp"].max()
    current_price = float(clean.sort_values("timestamp")[price_col].iloc[-1])

    profile = compute_seasonal_profile(clean, price_col)
    if profile.n_days < min_history_days:
        raise InsufficientDataError(
            f"Nur {profile.n_days} Tage Historie vorhanden, mindestens {min_history_days} erforderlich."
        )

    trend_per_day = compute_trend_per_day(clean, price_col)
    target_ts = now + timedelta(hours=horizon_hours)

    trend_component = trend_per_day * (horizon_hours / 24.0)
    seasonal_component = _seasonal_deviation(profile, target_ts) - _seasonal_deviation(profile, now)

    predicted = current_price + trend_component + seasonal_component
    predicted = float(np.clip(predicted, MIN_PLAUSIBLE_PRICE, MAX_PLAUSIBLE_PRICE))

    delta = predicted - current_price
    if delta > STABLE_THRESHOLD_EUR:
        direction: DIRECTION = "steigend"
    elif delta < -STABLE_THRESHOLD_EUR:
        direction = "fallend"
    else:
        direction = "stabil"

    bucket_std = _bucket_std(clean, price_col, target_ts.weekday(), target_ts.hour)
    confidence = heuristic_confidence(profile.n_days, bucket_std, min_history_days)

    return ForecastPoint(
        predicted_price=round(predicted, 3),
        direction=direction,
        confidence=confidence,
        method="weighted_moving_average+weekday_hour_seasonality+linear_trend",
    )


def best_refuel_window(
    df: pd.DataFrame,
    price_col: str,
    now: Optional[datetime] = None,
    horizon_hours: int = 48,
    window_hours: int = 2,
    min_history_days: int = 7,
) -> RefuelWindow:
    """Regelbasierte Empfehlung: welches Zeitfenster in den nächsten
    `horizon_hours` Stunden hat historisch/saisonal den günstigsten
    erwarteten Preis? Rein auf dem saisonalen Profil + Trend basierend,
    kein Modellaufruf."""
    clean = validate_and_clean(df, price_col)
    if clean.empty:
        raise InsufficientDataError("Keine validen Preisdaten vorhanden.")
    now = now or clean["timestamp"].max()
    current_price = float(clean.sort_values("timestamp")[price_col].iloc[-1])

    candidates: list[tuple[datetime, float]] = []
    for h in range(1, horizon_hours + 1):
        point = forecast(clean, price_col, horizon_hours=h, now=now, min_history_days=min_history_days)
        candidates.append((now + timedelta(hours=h), point.predicted_price))

    # gleitendes Fenster über die Kandidaten, um das günstigste zusammenhängende
    # Zeitfenster (nicht nur eine Einzelstunde) zu finden
    best_start_idx = 0
    best_avg = float("inf")
    for i in range(len(candidates) - window_hours + 1):
        window_prices = [p for _, p in candidates[i : i + window_hours]]
        avg = sum(window_prices) / len(window_prices)
        if avg < best_avg:
            best_avg = avg
            best_start_idx = i

    start_ts = candidates[best_start_idx][0]
    end_ts = candidates[min(best_start_idx + window_hours, len(candidates) - 1)][0]

    return RefuelWindow(
        start=start_ts,
        end=end_ts,
        expected_price=round(best_avg, 3),
        expected_savings_vs_now=round(current_price - best_avg, 3),
    )
