"""
Zentrale Konfiguration der Anwendung.

Alle Werte sind von außen konfigurierbar (Umgebungsvariablen / .env-Datei),
damit z.B. das lokale Sprachmodell oder der Inference-Server ausgetauscht
werden kann, ohne den Code zu ändern (siehe Anforderung "extern konfigurierbar").
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Anwendung ---
    app_name: str = "Benzinpreis-Assistent"
    environment: str = "development"

    # --- Datenbank ---
    database_url: str = "sqlite:///./data/app.db"

    # --- Lokale KI-Komponente (OpenAI-kompatible API, z.B. Ollama) ---
    ai_base_url: str = "http://localhost:11434/v1"
    ai_model: str = "gemma3n:e4b"
    ai_api_key: str = "not-needed-for-local-inference"
    ai_timeout_seconds: float = 20.0
    ai_max_retries: int = 1

    # --- Forecasting ---
    forecast_horizon_hours: int = 24
    min_history_days_for_forecast: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
