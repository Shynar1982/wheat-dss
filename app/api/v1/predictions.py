from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.services.yield_predictor import YieldPrediction

router = APIRouter(prefix="/v1/fields", tags=["yield"])

@router.get("/{field_id}/yield/predictions")
async def get_predictions(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(YieldPrediction).where(YieldPrediction.field_id == field_id).order_by(YieldPrediction.id.desc())
    result = await db.execute(stmt)
    return result.scalars().all()
