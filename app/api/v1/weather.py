from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.services.weather_client import WeatherDaily

router = APIRouter(prefix="/v1/fields", tags=["weather"])

@router.get("/{field_id:int}/weather")
async def get_field_weather(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(WeatherDaily).where(WeatherDaily.field_id == field_id).order_by(WeatherDaily.obs_date)
    result = await db.execute(stmt)
    weather = result.scalars().all()
    if not weather:
        raise HTTPException(status_code=404, detail="Данные о погоде не найдены")
    return weather
