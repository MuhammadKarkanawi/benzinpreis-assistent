from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.ai.client import AIClient
from app.ai.qa import answer_question
from app.config import Settings, get_settings
from app.db import get_session
from app.schemas import AskRequest, AskResponse

router = APIRouter(prefix="/ask", tags=["KI-Assistent"])


def get_ai_client(settings: Settings = Depends(get_settings)) -> AIClient:
    return AIClient(settings)


@router.post("", response_model=AskResponse)
async def ask(
    request: AskRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    ai_client: AIClient = Depends(get_ai_client),
):
    result = await answer_question(
        session=session,
        settings=settings,
        ai_client=ai_client,
        station_uuid=request.station_uuid,
        fuel_type=request.fuel_type,
        question=request.question,
        use_context=request.use_context,
    )
    return AskResponse(**result)
