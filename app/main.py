import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.ai.client import AIClient
from app.config import get_settings
from app.data_loader import seed_from_csv
from app.db import engine, init_db
from app.routers import ask, forecast, health, prices, stations

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"


async def _warm_up_ai_backend() -> None:
    """Feuert einmalig einen (nicht abgewarteten) Testaufruf an die lokale
    KI-Komponente ab, damit ein echter Inference-Server (z.B. Ollama) das
    Modell schon während des App-Starts laedt, statt erst beim ersten
    echten Nutzer-Request - sonst kann dieser aufgrund des Kaltstarts in
    ein Timeout laufen, obwohl der Server grundsaetzlich erreichbar ist.
    Rein "best effort": Fehler (z.B. Server noch nicht bereit) werden nur
    geloggt, blockieren den App-Start aber nicht. Gefunden bei der
    KI-Evaluation mit dem echten Modell, siehe AI_DEVELOPMENT_LOG.md
    Episode 7."""
    try:
        client = AIClient(get_settings())
        await client.chat([{"role": "user", "content": "Hallo"}])
        print("[startup] KI-Backend erfolgreich vorgewaermt.")
    except Exception as exc:  # noqa: BLE001 - Warm-up ist bewusst best-effort
        print(f"[startup] KI-Warm-up fehlgeschlagen (ignoriert): {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        try:
            result = seed_from_csv(session, DATA_DIR)
            print(f"[startup] Seed-Ergebnis: {result}")
        except FileNotFoundError as exc:
            print(f"[startup] Warnung: {exc}")
    warm_up_task = asyncio.create_task(_warm_up_ai_backend())
    try:
        yield
    finally:
        warm_up_task.cancel()


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


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Zentrale Behandlung fehlschlagender Datenbankzugriffe (Anforderung
    "Failure handling": persistierte Daten nicht lesbar/schreibbar) - z.B.
    eine gesperrte oder beschädigte SQLite-Datei. Ohne diesen Handler würde
    ein solcher Fehler als unbehandelte 500-Exception mit Stacktrace
    durchschlagen statt als kontrollierte, für Clients auswertbare Antwort.
    Gilt einheitlich für alle Endpunkte, die über `Depends(get_session)`
    auf die Datenbank zugreifen (/stations, /prices, /forecast, /ask)."""
    print(f"[error] Datenbankzugriff fehlgeschlagen: {exc}")
    return JSONResponse(
        status_code=503,
        content={"detail": "Datenbank aktuell nicht verfügbar. Bitte später erneut versuchen."},
    )


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(BASE_DIR / "static" / "index.html")
