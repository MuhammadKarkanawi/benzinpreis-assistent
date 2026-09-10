from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models import Station
from app.schemas import StationOut

router = APIRouter(prefix="/stations", tags=["Tankstellen"])


@router.get("", response_model=list[StationOut])
def list_stations(session: Session = Depends(get_session)):
    return session.exec(select(Station)).all()
