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

router = APIRouter(tags=["live"])

@router.get("/api/fields/{field_id}/info")
async def get_field_info(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(Field.field_id, Field.name, Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    row = result.first()
    if not row: raise HTTPException(status_code=404, detail="Field not found")
    return {"field_id": row[0], "name": row[1], "area_ha": float(row[2]) if row[2] else 0, "region": "Костанайская обл.", "district": "Костанайский р-н"}

@router.get("/api/fields/{field_id}/fertilizer")
async def get_fertilizer_recommendation(field_id: int, sim_month: int = Query(0)):
    month = sim_month if sim_month != 0 else datetime.datetime.now().month
    if month >= 11 or month <= 2:
        return {"status": "winter", "message": "Зимний период: внесение удобрений не требуется.", "recommendations": []}
    
    # Берем реальную площадь (или ставим 20 для демо)
    area_ha = 20.0 
    predicted_yield = 4.125
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
async def get_agro_forecast(field_id: int, sim_month: int = Query(0)):
    current_month = sim_month if sim_month != 0 else datetime.datetime.now().month
    today = datetime.date(2024, current_month, 15) if current_month != 0 else datetime.date.today()
    result_data = {}
    
    if today > datetime.date(2024, 5, 25):
        result_data["sowing"] = {"status": "missed", "message": "Посевное окно завершено.", "details": ""}
    elif today < datetime.date(2024, 5, 10):
        result_data["sowing"] = {"status": "early", "message": "До посева еще далеко.", "details": ""}
    else:
        result_data["sowing"] = {"status": "success", "message": "Успеваем! Начало сева: 17.05.", "details": "Площадь 20 га. Сев займет 1 дн."}

    if today < datetime.date(2024, 8, 10):
        result_data["harvest"] = {"status": "early", "message": "Уборка еще не началась.", "details": ""}
    elif today > datetime.date(2024, 9, 20):
        result_data["harvest"] = {"status": "missed", "message": "Уборка завершена.", "details": ""}
    else:
        result_data["harvest"] = {"status": "success", "message": "Успеваем! Начало уборки: 15.09.", "details": "Уборка займет 2 дн."}
    return result_data

@router.get("/api/fields/{field_id}/real_data")
async def get_real_data(field_id: int):
    # 1. ЧИТАЕМ РЕАЛЬНЫЙ NDVI ИЗ CSV
    ndvi_data = []
    csv_path = 'data/features/master_dataset.csv'
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        # Ищем строку по id (или берем первую, если id не совпадает)
        row = df[df['id'] == field_id]
        if row.empty:
            row = df.head(1) # Если поля нет, берем первое для демо
        
        if not row.empty:
            r = row.iloc[0]
            # Формируем реальные точки по сезонам
            seasons = [
                ("2024-05-15", "s2_NDVI_spring"),
                ("2024-07-15", "s2_NDVI_summer"),
                ("2024-08-15", "s2_NDVI_late_summer"),
                ("2024-09-15", "s2_NDVI_autumn")
            ]
            for date_str, col_name in seasons:
                if col_name in r and pd.notna(r[col_name]):
                    ndvi_data.append({"observed_at": date_str, "ndvi": round(float(r[col_name]), 3)})

    # 2. ПОГОДА ИЗ OPEN-METEO (Реальный архив 2024)
    weather_data = []
    gdd_series = []
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude=52.9&longitude=66.2&start_date=2024-03-01&end_date=2024-09-30&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                raw = resp.json().get("daily", {})
                times, t_max, t_min, precip = raw.get("time", []), raw.get("temperature_2m_max", []), raw.get("temperature_2m_min", []), raw.get("precipitation_sum", [])
                
                gdd_cum = 0
                for i in range(len(times)):
                    day = {"obs_date": times[i], "t_max_c": t_max[i], "t_min_c": t_min[i], "precip_mm": precip[i]}
                    weather_data.append(day)
                    
                    if times[i] >= "2024-05-17" and t_max[i] is not None:
                        gdd_cum += max(0, ((t_max[i] + t_min[i]) / 2) - 5.0)
                    gdd_series.append({"obs_date": times[i], "gdd_cum": round(gdd_cum, 2)})
    except Exception as e:
        print(f"Ошибка погоды: {e}")

    return {"weather": weather_data, "gdd": gdd_series, "ndvi": ndvi_data}
