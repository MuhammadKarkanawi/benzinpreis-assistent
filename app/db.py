"""Datenbank-Engine und Session-Handling."""
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine

from app.config import get_settings

settings = get_settings()

# Bei SQLite: Verzeichnis sicherstellen
if settings.database_url.startswith("sqlite:///"):
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path not in (":memory:",):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
