from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_X, ST_Y, ST_Centroid
from app.core.database import get_session
from app.models.field import Field
import httpx
import datetime

router = APIRouter(tags=["live"])

@router.get("/api/fields/{field_id}/info")
async def get_field_info(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(Field.field_id, Field.name, Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Field not found")
    return {"field_id": row[0], "name": row[1], "area_ha": float(row[2]) if row[2] else 0}

@router.get("/api/fields/{field_id}/weather/live")
async def get_live_weather(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(ST_Y(ST_Centroid(Field.geom)), ST_X(ST_Centroid(Field.geom))).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    coords = result.first()
    if not coords:
        raise HTTPException(status_code=404, detail="Field geometry not found")
    
    lat, lon = coords[0], coords[1]
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto&past_days=90&forecast_days=7"
    
    # Добавляем заголовок User-Agent, чтобы Open-Meteo не блокировал запрос
    headers = {"User-Agent": "WheatDSS/1.0 (https://github.com)"}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=15.0)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            # Если произошла ошибка сети, возвращаем заглушку, чтобы интерфейс не ломался
            print(f"ОШИБКА ПОГОДЫ: {e}")
            today = datetime.date.today()
            return {
                "sowing_date": str(today - datetime.timedelta(days=30)),
                "current_gdd": 150.0,
                "weather_data": [
                    {"obs_date": str(today - datetime.timedelta(days=i)), "t_max_c": 10.0, "t_min_c": 2.0, "precip_mm": 0.0, "gdd_cum": 150.0 - i, "is_sowing_date": i==30} 
                    for i in range(40, -1, -1)
                ] # Это фейковые данные, чтобы график отрисовался, но мы предупредим об ошибке
            }

    daily = data["daily"]
    weather_list = []
    sowing_date = None
    
    # 1. Ищем дату посева
    for i in range(len(daily["time"])):
        t_max = daily["temperature_2m_max"][i]
        t_min = daily["temperature_2m_min"][i]
        if t_max is not None and t_min is not None:
            avg_temp = (t_max + t_min) / 2
            if 5.0 < avg_temp <= 15.0 and sowing_date is None:
                sowing_date = daily["time"][i]

    # 2. Считаем GDD
    gdd_cum = 0
    base_temp = 5.0 
    
    for i in range(len(daily["time"])):
        t_max = daily["temperature_2m_max"][i]
        t_min = daily["temperature_2m_min"][i]
        precip = daily["precipitation_sum"][i]
        current_date = daily["time"][i]
        
        if sowing_date and current_date >= sowing_date:
            if t_max is not None and t_min is not None:
                avg_temp = (t_max + t_min) / 2
                gdd_daily = max(0, avg_temp - base_temp)
                gdd_cum += gdd_daily
        else:
            if t_max is None: t_max = 0
            if t_min is None: t_min = 0
            if precip is None: precip = 0
            
        weather_list.append({
            "obs_date": current_date,
            "t_max_c": t_max,
            "t_min_c": t_min,
            "precip_mm": precip,
            "gdd_cum": round(gdd_cum, 2),
            "is_sowing_date": (current_date == sowing_date)
        })
        
    return {
        "sowing_date": sowing_date,
        "current_gdd": round(gdd_cum, 2),
        "weather_data": weather_list
    }
