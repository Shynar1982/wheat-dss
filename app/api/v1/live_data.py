from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_X, ST_Y, ST_Centroid
from app.core.database import get_session
from app.models.field import Field
import httpx
import datetime
import math
import random

router = APIRouter(tags=["live"])

@router.get("/api/fields/{field_id}/info")
async def get_field_info(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(Field.field_id, Field.name, Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Field not found")

    stmt_coords = select(ST_Y(ST_Centroid(Field.geom)), ST_X(ST_Centroid(Field.geom))).where(Field.field_id == field_id)
    result_coords = await db.execute(stmt_coords)
    coords = result_coords.first()

    region = "Не определён"
    district = "Не определён"

    if coords:
        lat, lon = coords[0], coords[1]
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10&addressdetails=1"
        headers = {"User-Agent": "WheatDSS/1.0"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    address = data.get("address", {})
                    region = address.get("state", "Не определён")
                    district = address.get("county", address.get("city_district", "Не определён"))
        except Exception as e:
            pass

    return {
        "field_id": row[0], "name": row[1], "area_ha": float(row[2]) if row[2] else 0,
        "region": region, "district": district
    }

def generate_mock_weather(start_date, end_date):
    """Генерирует реалистичную погоду, если внешний API недоступен"""
    weather_data = []
    gdd_data = []
    gdd_cum = 0
    base_temp = 5.0
    
    current_date = start_date
    while current_date <= end_date:
        # Генерируем температуру по синусоиде (холодно в марте, жарко в июле)
        day_of_year = current_date.timetuple().tm_yday
        # Синусоида: от 5 градусов в марте до 28 в июле
        t_max = 15 + 13 * math.sin(2 * math.pi * (day_of_year - 100) / 365)
        t_min = t_max - 8 - random.uniform(0, 5)
        precip = random.uniform(0, 5) if random.random() > 0.7 else 0.0
        
        avg_temp = (t_max + t_min) / 2
        if avg_temp >= base_temp:
            gdd_cum += max(0, avg_temp - base_temp)
            
        date_str = current_date.strftime("%Y-%m-%d")
        weather_data.append({
            "obs_date": date_str, "t_max_c": round(t_max, 1), "t_min_c": round(t_min, 1), "precip_mm": round(precip, 1)
        })
        gdd_data.append({"obs_date": date_str, "gdd_cum": round(gdd_cum, 2)})
        
        current_date += datetime.timedelta(days=1)
        
    return weather_data, gdd_data

@router.get("/api/fields/{field_id}/weather/historical")
async def get_historical_weather(
    field_id: int, 
    sim_month: int = Query(0, description="Симуляция месяца (0 - реальный, 1-12)"),
    db: AsyncSession = Depends(get_session)
):
    stmt = select(ST_Y(ST_Centroid(Field.geom)), ST_X(ST_Centroid(Field.geom))).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    coords = result.first()
    if not coords:
        raise HTTPException(status_code=404, detail="Field geometry not found")
    
    lat, lon = coords[0], coords[1]
    current_month = sim_month if sim_month != 0 else datetime.datetime.now().month
    sim_year = 2024

    start_date_obj = datetime.date(sim_year, 3, 1)
    end_date_obj = datetime.date(sim_year, 10, 1)
    
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date_obj}&end_date={end_date_obj}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
    headers = {"User-Agent": "WheatDSS/1.0"}
    
    weather_list = []
    gdd_list = []
    sowing_date = None
    gdd_cum = 0
    base_temp = 5.0 

    api_success = False
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                daily = response.json().get("daily", {})
                if daily and daily.get("time"):
                    for i in range(len(daily["time"])):
                        t_max = daily["temperature_2m_max"][i]
                        t_min = daily["temperature_2m_min"][i]
                        precip = daily["precipitation_sum"][i]
                        current_date_str = daily["time"][i]
                        
                        if t_max is not None and t_min is not None:
                            avg_temp = (t_max + t_min) / 2
                            if current_date_str[5:7] in ['03', '04', '05'] and avg_temp >= 5.0 and sowing_date is None:
                                sowing_date = current_date_str
                                
                        if sowing_date and current_date_str >= sowing_date:
                            if t_max is not None and t_min is not None:
                                avg_temp = (t_max + t_min) / 2
                                gdd_cum += max(0, avg_temp - base_temp)
                                
                        weather_list.append({"obs_date": current_date_str, "t_max_c": t_max or 0, "t_min_c": t_min or 0, "precip_mm": precip or 0})
                        gdd_list.append({"obs_date": current_date_str, "gdd_cum": round(gdd_cum, 2)})
                    api_success = True
    except Exception as e:
        pass

    # Если внешний API упал или вернул пустоту, включаем генератор
    if not api_success or not weather_list:
        weather_list, gdd_list = generate_mock_weather(start_date_obj, end_date_obj)
        # Находим дату посева в сгенерированных данных
        for w in weather_list:
            if w["obs_date"][5:7] in ['03', '04', '05'] and w["t_max_c"] >= 10.0: # Условный порог для мока
                sowing_date = w["obs_date"]
                break
        # Пересчитываем GDD до конца для мока
        gdd_cum = gdd_list[-1]["gdd_cum"] if gdd_list else 0

    return {
        "current_month": current_month,
        "sowing_date": sowing_date,
        "current_gdd": round(gdd_cum, 2),
        "weather_data": weather_list,
        "gdd_data": gdd_list
    }

@router.get("/api/fields/{field_id}/weeds")
async def get_weed_analysis(field_id: int, sim_month: int = Query(0)):
    month = sim_month if sim_month != 0 else datetime.datetime.now().month
    if month >= 11 or month <= 2:
        return {"field_id": field_id, "weed_percentage": 0, "status": "Сезон завершен", "recommendation": "Зимний период: сорняки в состоянии покоя."}
        
    weed_percentage = (field_id % 20) + 5.5 
    if weed_percentage > 15:
        return {"field_id": field_id, "weed_percentage": round(weed_percentage, 1), "status": "Высокая", "recommendation": "Рекомендуется дифференцированная обработка гербицидами (VRT)."}
    elif weed_percentage > 8:
        return {"field_id": field_id, "weed_percentage": round(weed_percentage, 1), "status": "Средняя", "recommendation": "Рекомендуется выборочная обработка или боронование."}
    else:
        return {"field_id": field_id, "weed_percentage": round(weed_percentage, 1), "status": "Низкая", "recommendation": "Химическая обработка не требуется."}
