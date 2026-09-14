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
    ai_model: str = "gemma3:4b"
    ai_api_key: str = "not-needed-for-local-inference"
    ai_timeout_seconds: float = 20.0
    ai_max_retries: int = 1

    # --- Forecasting ---
    forecast_horizon_hours: int = 24
    min_history_days_for_forecast: int = 7

    # --- Echte Tankerkönig-Daten sammeln (optional, siehe scripts/collect_real_prices.py) ---
    # Leer = Sammel-Skripte sind deaktiviert (Standard, da kostenpflichtige
    # Registrierung bei Tankerkönig zum Zeitpunkt der Entwicklung wegen
    # Wartungsarbeiten nicht möglich war - siehe AI_DEVELOPMENT_LOG.md,
    # Episode 9). Sobald ein Key vorliegt, hier eintragen.
    tankerkoenig_api_key: str = ""
    # Komma-getrennte Liste echter Tankstellen-UUIDs (von Tankerkönig), deren
    # Preise gesammelt werden sollen. Wird von
    # scripts/discover_real_stations.py befüllt.
    tankerkoenig_station_uuids: str = ""
    # Timeout für Aufrufe der Tankerkönig-API in Sekunden. Der ursprüngliche,
    # fest codierte 10s-Timeout im Client war beim ersten echten Sammel-Lauf
    # tatsächlich einmal zu knapp (siehe AI_DEVELOPMENT_LOG.md, Episode 10) -
    # deshalb konfigurierbar, analog zu ai_timeout_seconds.
    tankerkoenig_timeout_seconds: float = 15.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
