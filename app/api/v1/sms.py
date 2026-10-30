from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.services.recommendation_engine import Recommendation
from app.services.sms_sender import send_sms

router = APIRouter(prefix="/v1/fields", tags=["sms"])

@router.post("/{field_id:int}/send_sms")
async def send_recommendation_sms(field_id: int, phone: str, db: AsyncSession = Depends(get_session)):
    # Находим последнюю рекомендацию
    stmt = select(Recommendation).where(Recommendation.field_id == field_id).order_by(Recommendation.id.desc()).limit(1)
    rec = (await db.execute(stmt)).scalars().first()
    
    if not rec:
        raise HTTPException(404, "Нет рекомендаций для отправки")
        
    success = await send_sms(phone, rec.message_text)
    if success:
        return {"status": "success", "message": "SMS успешно отправлено"}
    else:
        raise HTTPException(500, "Ошибка отправки SMS")
