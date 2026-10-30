from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.services.gee_client import SpectralIndex

router = APIRouter(prefix="/v1/fields", tags=["indices"])

@router.get("/{field_id}/indices")
async def get_field_indices(
    field_id: int, 
    start_date: str | None = None, 
    end_date: str | None = None, 
    db: AsyncSession = Depends(get_session)
):
    stmt = select(SpectralIndex).where(SpectralIndex.field_id == field_id)
    
    if start_date:
        stmt = stmt.where(SpectralIndex.observed_at >= start_date)
    if end_date:
        stmt = stmt.where(SpectralIndex.observed_at <= end_date)
        
    stmt = stmt.order_by(SpectralIndex.observed_at)
    
    result = await db.execute(stmt)
    indices = result.scalars().all()
    
    if not indices:
        raise HTTPException(status_code=404, detail="Данные не найдены")
        
    return indices
