from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_X, ST_Y, ST_Centroid, ST_AsGeoJSON
from app.core.database import get_session
from app.models.field import Field
import httpx
import datetime
import math
import json

router = APIRouter(tags=["live"])

@router.get("/api/fields/{field_id}/info")
async def get_field_info(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(Field.field_id, Field.name, Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    row = result.first()
    if not row: raise HTTPException(status_code=404, detail="Field not found")

    stmt_coords = select(ST_Y(ST_Centroid(Field.geom)), ST_X(ST_Centroid(Field.geom))).where(Field.field_id == field_id)
    result_coords = await db.execute(stmt_coords)
    coords = result_coords.first()
    lat, lon = (coords[0], coords[1]) if coords else (52.9, 66.2)

    region, district = "Не определён", "Не определён"
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10&addressdetails=1"
        headers = {"User-Agent": "WheatDSS/1.0"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json().get("address", {})
                region = data.get("state", "Не определён")
                district = data.get("county", "Не определён")
    except Exception: pass

    return {"field_id": row[0], "name": row[1], "area_ha": float(row[2]) if row[2] else 0, "region": region, "district": district}

@router.get("/api/fields/{field_id}/fertilizer")
async def get_fertilizer_recommendation(field_id: int, sim_month: int = Query(0), db: AsyncSession = Depends(get_session)):
    stmt = select(Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    area_ha = result.scalar() or 20.0
    month = sim_month if sim_month != 0 else datetime.datetime.now().month

    if month >= 11 or month <= 2:
        return {"status": "winter", "message": "Зимний период: внесение удобрений не требуется.", "recommendations": []}

    predicted_yield = 4.131
    total_n, total_p, total_k = predicted_yield * 27, predicted_yield * 11.5, predicted_yield * 20.5
    n_pre, n_top = total_n * 0.6, total_n * 0.4
    
    recs = [
        {"phase": "Предпосевное", "nutrient": "Фосфор (P₂O₅)", "dose_kg_ha": round(total_p / area_ha, 1), "total_kg": round(total_p, 1), "note": "Под культивацию."},
        {"phase": "Предпосевное", "nutrient": "Калий (K₂O)", "dose_kg_ha": round(total_k / area_ha, 1), "total_kg": round(total_k, 1), "note": "Под культивацию."},
        {"phase": "Предпосевное", "nutrient": "Азот (N)", "dose_kg_ha": round(n_pre / area_ha, 1), "total_kg": round(n_pre, 1), "note": "60% от нормы."},
        {"phase": "Подкормка (кущение)", "nutrient": "Азот (N)", "dose_kg_ha": round(n_top / area_ha, 1), "total_kg": round(n_top, 1), "note": "40% от нормы."}
    ]
    return {"status": "success", "message": f"Урожайность: {predicted_yield:.1f} т/га. Потребность: {round(total_n+total_p+total_k,1)} кг.", "recommendations": recs}

@router.get("/api/fields/{field_id}/weeds")
async def get_weed_analysis(field_id: int, sim_month: int = Query(0)):
    month = sim_month if sim_month != 0 else datetime.datetime.now().month
    if month >= 11 or month <= 2:
        return {"status": "winter", "message": "Сезон завершен."}
    return {"status": "success", "weed_percentage": 12.0, "risk_level": "Средняя", "recommendation": "Выборочная обработка.", "chemical": "Линтур (0.15 кг/га)"}

@router.get("/api/fields/{field_id}/agro_forecast")
async def get_agro_forecast(field_id: int, sim_month: int = Query(0), db: AsyncSession = Depends(get_session)):
    stmt = select(Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    area_ha = result.scalar() or 20.0
    current_month = sim_month if sim_month != 0 else datetime.datetime.now().month
    today = datetime.date(2024, current_month, 15) if current_month != 0 else datetime.date.today()

    SOWING_RATE, HARVEST_RATE = 50.0, 15.0
    sowing_days = math.ceil(area_ha / SOWING_RATE)
    harvest_days = math.ceil(area_ha / HARVEST_RATE)
    result_data = {}

    sowing_start, sowing_end = datetime.date(2024, 5, 10), datetime.date(2024, 5, 25)
    if today > sowing_end:
        result_data["sowing"] = {"status": "missed", "message": "Посевное окно завершено.", "details": ""}
    elif today < sowing_start:
        result_data["sowing"] = {"status": "early", "message": f"До посева {(sowing_start - today).days} дней.", "details": f"Сев займет {sowing_days} дн."}
    else:
        best_sowing_day = min(today + datetime.timedelta(days=2), sowing_end)
        end_sowing_date = best_sowing_day + datetime.timedelta(days=sowing_days)
        if end_sowing_date <= sowing_end:
            result_data["sowing"] = {"status": "success", "message": f"Успеваем! Начало сева: {best_sowing_day.strftime('%d.%m')}.", "details": f"Сев займет {sowing_days} дн. Завершение: {end_sowing_date.strftime('%d.%m')}."}
        else:
            result_data["sowing"] = {"status": "risk", "message": f"Риск! Начало сева: {best_sowing_day.strftime('%d.%m')}.", "details": f"Сев займет {sowing_days} дн. Завершение выходит за пределы!"}

    harvest_start, harvest_end = datetime.date(2024, 8, 10), datetime.date(2024, 9, 20)
    if today < harvest_start:
        result_data["harvest"] = {"status": "early", "message": "Уборка еще не началась.", "details": f"Ожидаемая продолжительность: {harvest_days} дн."}
    elif today > harvest_end:
        result_data["harvest"] = {"status": "missed", "message": "Уборочная кампания завершена.", "details": ""}
    else:
        best_harvest_day = min(today + datetime.timedelta(days=1), harvest_end)
        end_harvest_date = best_harvest_day + datetime.timedelta(days=harvest_days)
        if end_harvest_date <= harvest_end:
            result_data["harvest"] = {"status": "success", "message": f"Успеваем! Начало уборки: {best_harvest_day.strftime('%d.%m')}.", "details": f"Уборка займет {harvest_days} дн."}
        else:
            result_data["harvest"] = {"status": "risk", "message": f"Риск! Начало уборки: {best_harvest_day.strftime('%d.%m')}.", "details": f"Уборка займет {harvest_days} дн. Завершение выходит за пределы!"}

    return result_data

@router.get("/api/fields/{field_id}/real_data")
async def get_real_data(field_id: int, db: AsyncSession = Depends(get_session)):
    # Для демо используем координаты Давыденовки
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude=52.9&longitude=66.2&start_date=2024-03-01&end_date=2024-09-30&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
    weather_data = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                raw = resp.json().get("daily", {})
                times, t_max, t_min, precip = raw.get("time", []), raw.get("temperature_2m_max", []), raw.get("temperature_2m_min", []), raw.get("precipitation_sum", [])
                for i in range(len(times)):
                    weather_data.append({"obs_date": times[i], "t_max_c": t_max[i], "t_min_c": t_min[i], "precip_mm": precip[i]})
    except Exception: pass
    
    sowing_date = "2024-05-17" # Фиксируем для демо
    gdd_series, gdd_cum = [], 0
    for day in weather_data:
        date_str = day["obs_date"]
        if date_str >= sowing_date and day["t_max_c"] is not None:
            gdd_cum += max(0, ((day["t_max_c"] + day["t_min_c"]) / 2) - 5.0)
        gdd_series.append({"obs_date": date_str, "gdd_cum": round(gdd_cum, 2)})
    
    return {"weather": weather_data, "gdd": gdd_series, "sowing_date": sowing_date, "current_gdd": round(gdd_cum, 2)}
