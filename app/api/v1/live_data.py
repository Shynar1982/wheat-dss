from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_X, ST_Y, ST_Centroid
from app.core.database import get_session
from app.models.field import Field
import httpx
import datetime
import math
import pandas as pd
import os
import random

router = APIRouter(tags=["live"])

def get_ndvi_from_csv(field_id, year):
    csv_path = 'data/features/master_dataset.csv'
    if not os.path.exists(csv_path): return None
    try:
        df = pd.read_csv(csv_path)
        row = df[df['id'] == field_id]
        if 'year' in df.columns:
            row = row[row['year'] == int(year)]
        
        if row.empty: return None
        r = row.iloc[0]
        
        ndvi_cols = ["s2_NDVI_spring", "s2_NDVI_summer", "s2_NDVI_late_summer", "s2_NDVI_autumn"]
        if any(pd.notna(r[col]) for col in ndvi_cols if col in r):
            return {
                "spring": float(r.get("s2_NDVI_spring", 0)) if pd.notna(r.get("s2_NDVI_spring")) else None,
                "summer": float(r.get("s2_NDVI_summer", 0)) if pd.notna(r.get("s2_NDVI_summer")) else None,
                "late_summer": float(r.get("s2_NDVI_late_summer", 0)) if pd.notna(r.get("s2_NDVI_late_summer")) else None,
                "autumn": float(r.get("s2_NDVI_autumn", 0)) if pd.notna(r.get("s2_NDVI_autumn")) else None,
            }
    except Exception as e:
        print(f"Ошибка чтения CSV: {e}")
    return None

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
            resp = await client.get(url, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json().get("address", {})
                region = data.get("state", "Не определён")
                district = data.get("county", "Не определён")
    except Exception: pass

    return {"field_id": row[0], "name": row[1], "area_ha": float(row[2]) if row[2] else 0, "region": region, "district": district}

@router.get("/api/fields/{field_id}/weeds")
async def get_weed_analysis(field_id: int, target_date: str = Query(None)):
    if not target_date:
        target_date = datetime.date.today().isoformat()
    
    date_obj = datetime.date.fromisoformat(target_date)
    month = date_obj.month
    year = date_obj.year
    
    if month in [9, 10, 11, 12, 1, 2]:
        return {"status": "winter", "message": "Сезон завершен или уборка. Обработка не требуется."}
    
    ndvi_data = get_ndvi_from_csv(field_id, year)
    
    if not ndvi_data or ndvi_data["spring"] is None:
        return {"status": "no_data", "message": f"Нет архивных данных NDVI за {year} год."}

    current_ndvi = ndvi_data["spring"]
    weed_percentage = max(0, round((0.6 - current_ndvi) * 100, 1))
    
    if weed_percentage > 20:
        status, rec, chem = "Высокая", "Рекомендуется дифференцированная обработка гербицидами (VRT).", "Балерина (0.3-0.4 л/га)"
    elif weed_percentage > 10:
        status, rec, chem = "Средняя", "Рекомендуется выборочная обработка.", "Линтур (0.15 кг/га)"
    else:
        status, rec, chem = "Низкая", "Химическая обработка не требуется.", "Не требуется"

    return {"status": "success", "weed_percentage": weed_percentage, "risk_level": status, "recommendation": rec, "chemical": chem, "ndvi_source": current_ndvi}

@router.get("/api/fields/{field_id}/fertilizer")
async def get_fertilizer_recommendation(field_id: int, target_date: str = Query(None), db: AsyncSession = Depends(get_session)):
    if not target_date:
        target_date = datetime.date.today().isoformat()
    
    date_obj = datetime.date.fromisoformat(target_date)
    month = date_obj.month
    
    stmt = select(Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    area_ha = result.scalar() or 20.0

    if month in [9, 10, 11, 12, 1, 2]:
        return {"status": "winter", "message": "Внесение удобрений не требуется.", "recommendations": []}

    predicted_yield = None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://localhost:8000/v1/fields/{field_id}/yield/predictions", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    predicted_yield = float(data[0]["predicted_yield_t_ha"])
    except Exception: pass

    if not predicted_yield:
        return {"status": "no_data", "message": "Нет прогноза урожайности.", "recommendations": []}

    total_n, total_p, total_k = predicted_yield * 27, predicted_yield * 11.5, predicted_yield * 20.5
    n_pre, n_top = total_n * 0.6, total_n * 0.4
    
    recs = [
        {"phase": "Предпосевное", "nutrient": "Фосфор (P₂O₅)", "dose_kg_ha": round(total_p / area_ha, 1), "total_kg": round(total_p, 1), "note": "Под культивацию."},
        {"phase": "Предпосевное", "nutrient": "Калий (K₂O)", "dose_kg_ha": round(total_k / area_ha, 1), "total_kg": round(total_k, 1), "note": "Под культивацию."},
        {"phase": "Предпосевное", "nutrient": "Азот (N)", "dose_kg_ha": round(n_pre / area_ha, 1), "total_kg": round(n_pre, 1), "note": "60% от нормы."},
        {"phase": "Подкормка (кущение)", "nutrient": "Азот (N)", "dose_kg_ha": round(n_top / area_ha, 1), "total_kg": round(n_top, 1), "note": "40% от нормы."}
    ]
    return {"status": "success", "message": f"Прогноз урожайности: {predicted_yield:.3f} т/га.", "recommendations": recs}

@router.get("/api/fields/{field_id}/agro_forecast")
async def get_agro_forecast(field_id: int, target_date: str = Query(None), db: AsyncSession = Depends(get_session)):
    if not target_date:
        target_date = datetime.date.today().isoformat()
    
    date_obj = datetime.date.fromisoformat(target_date)
    year = date_obj.year
    
    stmt = select(Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    area_ha = result.scalar() or 20.0
    
    result_data = {}
    
    sowing_start, sowing_end = datetime.date(year, 5, 10), datetime.date(year, 5, 25)
    harvest_start, harvest_end = datetime.date(year, 8, 10), datetime.date(year, 9, 20)

    SOWING_RATE, HARVEST_RATE = 50.0, 15.0
    sowing_days = math.ceil(area_ha / SOWING_RATE)
    harvest_days = math.ceil(area_ha / HARVEST_RATE)

    if date_obj > sowing_end:
        result_data["sowing"] = {"status": "missed", "message": "Посевное окно завершено.", "details": ""}
    elif date_obj < sowing_start:
        result_data["sowing"] = {"status": "early", "message": f"До посева {(sowing_start - date_obj).days} дней.", "details": f"Сев займет {sowing_days} дн."}
    else:
        result_data["sowing"] = {"status": "success", "message": f"Идет посевная. Сев займет {sowing_days} дн.", "details": f"(Окно: 10.05 - 25.05)"}

    if date_obj < harvest_start:
        result_data["harvest"] = {"status": "early", "message": "Уборка еще не началась.", "details": f"Ожидаемая продолжительность: {harvest_days} дн."}
    elif date_obj > harvest_end:
        result_data["harvest"] = {"status": "missed", "message": "Уборочная кампания завершена.", "details": ""}
    else:
        result_data["harvest"] = {"status": "success", "message": f"Идет уборка. Займет {harvest_days} дн.", "details": f"(Окно: 10.08 - 20.09)"}

    return result_data

@router.get("/api/fields/{field_id}/real_data")
async def get_real_data(field_id: int, target_date: str = Query(None), db: AsyncSession = Depends(get_session)):
    if not target_date:
        target_date = datetime.date.today().isoformat()
    
    date_obj = datetime.date.fromisoformat(target_date)
    year = date_obj.year
    
    stmt_coords = select(ST_Y(ST_Centroid(Field.geom)), ST_X(ST_Centroid(Field.geom))).where(Field.field_id == field_id)
    result_coords = await db.execute(stmt_coords)
    coords = result_coords.first()
    lat, lon = (coords[0], coords[1]) if coords else (52.9, 66.2)

    ndvi_data = []
    csv_ndvi = get_ndvi_from_csv(field_id, year)
    if csv_ndvi:
        seasons = [(f"{year}-05-15", csv_ndvi["spring"]), (f"{year}-07-15", csv_ndvi["summer"]), (f"{year}-08-15", csv_ndvi["late_summer"]), (f"{year}-09-15", csv_ndvi["autumn"])]
        for date_str, val in seasons:
            if val is not None:
                ndvi_data.append({"observed_at": date_str, "ndvi": round(val, 3)})

    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={year}-03-01&end_date={year}-09-30&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
    weather_data, gdd_series = [], []
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                raw = resp.json().get("daily", {})
                times, t_max, t_min, precip = raw.get("time", []), raw.get("temperature_2m_max", []), raw.get("temperature_2m_min", []), raw.get("precipitation_sum", [])
                gdd_cum = 0
                for i in range(len(times)):
                    weather_data.append({"obs_date": times[i], "t_max_c": t_max[i], "t_min_c": t_min[i], "precip_mm": precip[i]})
                    if times[i] >= f"{year}-05-17" and t_max[i] is not None:
                        gdd_cum += max(0, ((t_max[i] + t_min[i]) / 2) - 5.0)
                    gdd_series.append({"obs_date": times[i], "gdd_cum": round(gdd_cum, 2)})
    except Exception as e:
        print(f"Ошибка API: {e}")

    if not weather_data:
        start_date = datetime.date(year, 3, 1)
        gdd_cum = 0
        for i in range(214):
            current = start_date + datetime.timedelta(days=i)
            day_of_year = current.timetuple().tm_yday
            t_max = 15 + 13 * math.sin(2 * math.pi * (day_of_year - 100) / 365)
            t_min = t_max - 8 - random.uniform(0, 3)
            precip = 2.5 if i % 3 == 0 else 0.0
            weather_data.append({"obs_date": str(current), "t_max_c": round(t_max,1), "t_min_c": round(t_min,1), "precip_mm": precip})
            if str(current) >= f"{year}-05-17":
                gdd_cum += max(0, ((t_max + t_min) / 2) - 5.0)
            gdd_series.append({"obs_date": str(current), "gdd_cum": round(gdd_cum, 2)})

    return {"weather": weather_data, "gdd": gdd_series, "ndvi": ndvi_data}
