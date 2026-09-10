import httpx
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Station
from app.schemas import HealthOut

router = APIRouter(tags=["Status"])


@router.get("/health", response_model=HealthOut)
async def health(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    db_ok = True
    try:
        session.exec(select(Station).limit(1)).first()
    except Exception:
        db_ok = False

    ai_reachable: bool | None
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.ai_base_url.rstrip('/')}/models")
        ai_reachable = resp.status_code < 500
    except httpx.HTTPError:
        ai_reachable = False

    status = "ok" if db_ok and ai_reachable else "degraded"
    return HealthOut(
        status=status,
        database=db_ok,
        ai_backend_reachable=ai_reachable,
        ai_base_url=settings.ai_base_url,
        ai_model=settings.ai_model,
    )
