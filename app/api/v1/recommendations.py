from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.services.recommendation_engine import Recommendation

router = APIRouter(prefix="/v1/fields", tags=["recommendations"])

@router.get("/{field_id:int}/recommendations")
async def get_recommendations(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(Recommendation).where(Recommendation.field_id == field_id).order_by(Recommendation.generated_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()
