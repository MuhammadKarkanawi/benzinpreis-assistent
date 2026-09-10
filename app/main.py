from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.config import get_settings
from app.data_loader import seed_from_csv
from app.db import engine, init_db
from app.routers import ask, forecast, health, prices, stations

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        try:
            result = seed_from_csv(session, DATA_DIR)
            print(f"[startup] Seed-Ergebnis: {result}")
        except FileNotFoundError as exc:
            print(f"[startup] Warnung: {exc}")
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Nicht-KI-Kernlogik (Zeitreihen-Vorhersage, Tankzeit-Empfehlung) "
        "kombiniert mit einer lokal betriebenen, gegründeten (grounded) "
        "KI-Komponente zur Beantwortung von Fragen zu Kraftstoffpreisen."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(stations.router)
app.include_router(prices.router)
app.include_router(forecast.router)
app.include_router(ask.router)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(BASE_DIR / "static" / "index.html")
