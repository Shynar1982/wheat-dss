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

SENTINEL_AVAILABLE = False
try:
    import os
    from sentinelhub import SHConfig, SentinelHubStatistical, DataCollection, CRS, Geometry
    SENTINEL_AVAILABLE = True
    sh_config = SHConfig()
    sh_config.sh_client_id = os.getenv("SH_CLIENT_ID")
    sh_config.sh_client_secret = os.getenv("SH_CLIENT_SECRET")
    sh_config.sh_base_url = "https://sh.dataspace.copernicus.eu"
    sh_config.sh_auth_base_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
except ImportError:
    pass

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
    lat, lon = (coords[0], coords[1]) if coords else (52.9, 66.2)

    region = "Не определён"
    district = "Не определён"
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10&addressdetails=1"
        headers = {"User-Agent": "WheatDSS/1.0"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                address = data.get("address", {})
                region = address.get("state", "Не определён")
                district = address.get("county", address.get("city_district", "Не определён"))
    except Exception:
        pass

    return {"field_id": row[0], "name": row[1], "area_ha": float(row[2]) if row[2] else 0, "region": region, "district": district}

@router.get("/api/fields/{field_id}/fertilizer")
async def get_fertilizer_recommendation(field_id: int, sim_month: int = Query(0), db: AsyncSession = Depends(get_session)):
    stmt = select(Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    area_ha = result.scalar() or 20.0
    month = sim_month if sim_month != 0 else datetime.datetime.now().month

    if month >= 11 or month <= 2:
        return {"status": "winter", "message": "Зимний период: внесение удобрений не требуется.", "recommendations": []}

    predicted_yield = 4.125
    n_norm, p_norm, k_norm = 27, 11.5, 20.5
    total_n, total_p, total_k = predicted_yield * n_norm, predicted_yield * p_norm, predicted_yield * k_norm
    n_pre, n_top = total_n * 0.6, total_n * 0.4
    
    recs = [
        {"phase": "Предпосевное", "nutrient": "Фосфор (P₂O₅)", "dose_kg_ha": round(total_p / area_ha, 1), "total_kg": round(total_p, 1), "note": "Вносится под культивацию."},
        {"phase": "Предпосевное", "nutrient": "Калий (K₂O)", "dose_kg_ha": round(total_k / area_ha, 1), "total_kg": round(total_k, 1), "note": "Вносится под культивацию."},
        {"phase": "Предпосевное", "nutrient": "Азот (N)", "dose_kg_ha": round(n_pre / area_ha, 1), "total_kg": round(n_pre, 1), "note": "60% от нормы."},
        {"phase": "Подкормка (кущение)", "nutrient": "Азот (N)", "dose_kg_ha": round(n_top / area_ha, 1), "total_kg": round(n_top, 1), "note": "40% от нормы."}
    ]
    return {"status": "success", "message": f"Урожайность: {predicted_yield:.1f} т/га. Потребность: {round(total_n+total_p+total_k,1)} кг.", "recommendations": recs}

@router.get("/api/fields/{field_id}/weeds")
async def get_weed_analysis(field_id: int, sim_month: int = Query(0)):
    month = sim_month if sim_month != 0 else datetime.datetime.now().month
    if month >= 11 or month <= 2:
        return {"status": "winter", "message": "Сезон завершен."}
    return {"status": "success", "weed_percentage": 12.0, "risk_level": "Средняя", "recommendation": "Рекомендуется выборочная обработка.", "chemical": "Линтур (0.15 кг/га)"}

@router.get("/api/fields/{field_id}/agro_forecast")
async def get_agro_forecast(field_id: int, sim_month: int = Query(0), db: AsyncSession = Depends(get_session)):
    stmt = select(Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    area_ha = result.scalar() or 20.0
    current_month = sim_month if sim_month != 0 else datetime.datetime.now().month
    today = datetime.date(2024, current_month, 15) if current_month != 0 else datetime.date.today()

    SOWING_RATE = 50.0  
    HARVEST_RATE = 15.0 
    sowing_days = math.ceil(area_ha / SOWING_RATE)
    harvest_days = math.ceil(area_ha / HARVEST_RATE)
    result_data = {}

    sowing_start, sowing_end = datetime.date(2024, 5, 10), datetime.date(2024, 5, 25)
    if today > sowing_end:
        result_data["sowing"] = {"status": "missed", "message": "Посевное окно завершено.", "details": ""}
    elif today < sowing_start:
        result_data["sowing"] = {"status": "early", "message": f"До посева {(sowing_start - today).days} дней.", "details": f"Ожидаемая продолжительность сева: {sowing_days} дн. (площадь {area_ha:.1f} га)"}
    else:
        best_sowing_day = min(today + datetime.timedelta(days=2), sowing_end)
        end_sowing_date = best_sowing_day + datetime.timedelta(days=sowing_days)
        if end_sowing_date <= sowing_end:
            result_data["sowing"] = {"status": "success", "message": f"Успеваем! Начало сева: {best_sowing_day.strftime('%d.%m')}.", "details": f"Площадь {area_ha:.1f} га. Сев займет {sowing_days} дн. Завершение: {end_sowing_date.strftime('%d.%m')}."}
        else:
            result_data["sowing"] = {"status": "risk", "message": f"Риск! Начало сева: {best_sowing_day.strftime('%d.%m')}.", "details": f"Площадь {area_ha:.1f} га. Сев займет {sowing_days} дн. Завершение {end_sowing_date.strftime('%d.%m')} выходит за пределы (25.05)!"}

    harvest_start, harvest_end = datetime.date(2024, 8, 10), datetime.date(2024, 9, 20)
    if today < harvest_start:
        result_data["harvest"] = {"status": "early", "message": "Уборка еще не началась.", "details": f"Ожидаемая продолжительность: {harvest_days} дн. (площадь {area_ha:.1f} га)"}
    elif today > harvest_end:
        result_data["harvest"] = {"status": "missed", "message": "Уборочная кампания завершена.", "details": ""}
    else:
        best_harvest_day = min(today + datetime.timedelta(days=1), harvest_end)
        end_harvest_date = best_harvest_day + datetime.timedelta(days=harvest_days)
        if end_harvest_date <= harvest_end:
            result_data["harvest"] = {"status": "success", "message": f"Успеваем! Начало уборки: {best_harvest_day.strftime('%d.%m')}.", "details": f"Площадь {area_ha:.1f} га. Уборка займет {harvest_days} дн. Завершение: {end_harvest_date.strftime('%d.%m')}."}
        else:
            result_data["harvest"] = {"status": "risk", "message": f"Риск! Начало уборки: {best_harvest_day.strftime('%d.%m')}.", "details": f"Площадь {area_ha:.1f} га. Уборка займет {harvest_days} дн. Завершение {end_harvest_date.strftime('%d.%m')} выходит за пределы (20.09)!"}

    return result_data

@router.get("/api/fields/{field_id}/real_data")
async def get_real_data(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt_geom = select(ST_AsGeoJSON(Field.geom)).where(Field.field_id == field_id)
    result_geom = await db.execute(stmt_geom)
    geom_json = result_geom.scalar()
    if not geom_json:
        raise HTTPException(status_code=404, detail="Field geometry not found")
    geom_dict = json.loads(geom_json)
    
    start_date, end_date = "2024-03-01", "2024-09-30"
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude=52.9&longitude=66.2&start_date={start_date}&end_date={end_date}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
    weather_data = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=15.0)
            if resp.status_code == 200:
                raw = resp.json().get("daily", {})
                times = raw.get("time", [])
                t_max = raw.get("temperature_2m_max", [])
                t_min = raw.get("temperature_2m_min", [])
                precip = raw.get("precipitation_sum", [])
                for i in range(len(times)):
                    weather_data.append({"obs_date": times[i], "t_max_c": t_max[i] if i < len(t_max) else None, "t_min_c": t_min[i] if i < len(t_min) else None, "precip_mm": precip[i] if i < len(precip) else 0})
    except Exception: pass
    
    sowing_date = None
    for day in weather_data:
        if day["obs_date"] >= "2024-05-10" and day["t_max_c"] is not None and day["t_max_c"] >= 5.0:
            sowing_date = day["obs_date"]
            break
    
    gdd_series, gdd_cum = [], 0
    for day in weather_data:
        date_str = day["obs_date"]
        if sowing_date and date_str >= sowing_date and day["t_max_c"] is not None:
            avg_temp = (day["t_max_c"] + day["t_min_c"]) / 2
            gdd_cum += max(0, avg_temp - 5.0)
        gdd_series.append({"obs_date": date_str, "gdd_cum": round(gdd_cum, 2)})
    
    ndre_data = []
    ndre_mean = None
    weed_percentage = None
    n_dose = 0
    if SENTINEL_AVAILABLE:
        try:
            evalscript = "//VERSION=3\nfunction setup() { return { input: [{ bands: [\"B05\", \"B08\", \"dataMask\"] }], output: [{ id: \"ndre\", bands: 1, sampleType: \"FLOAT32\" }, { id: \"dataMask\", bands: 1 }] }; }\nfunction evaluatePixel(sample) { let ndre = (sample.B08 - sample.B05) / (sample.B08 + sample.B05); return { ndre: [ndre], dataMask: [sample.dataMask] }; }"
            geometry = Geometry(geom_dict, crs=CRS.WGS84)
            aggregation = SentinelHubStatistical.aggregation(evalscript=evalscript, time_interval=("2024-05-01", "2024-05-31"), aggregation_interval="P1D", size=[512, 512])
            request = SentinelHubStatistical(aggregation=aggregation, input_data=[SentinelHubStatistical.input_data(DataCollection.SENTINEL2_L2A, maxcc=0.3)], geometry=geometry, config=sh_config)
            response = request.get_data()
            for entry in response:
                for data_entry in entry['data']:
                    date_str = data_entry['interval']['from']
                    stats = data_entry['outputs']['ndre']['bands']['B0']['stats']
                    if stats and 'mean' in stats and stats['mean'] is not None:
                        ndre_data.append({"observed_at": date_str.split('T')[0], "ndre": round(stats['mean'], 4)})
            if ndre_data:
                ndre_mean = sum(d["ndre"] for d in ndre_data) / len(ndre_data)
                weed_percentage = max(0, round((0.6 - ndre_mean) * 100, 1))
                if sowing_date:
                    ndvi_proxy = min(1.0, ndre_mean * 1.2)
                    n_dose = max(0, min(120, round(274 - (11458 * ndvi_proxy / 30), 1)))
        except Exception: pass
        
    return {"weather": weather_data, "gdd": gdd_series, "sowing_date": sowing_date, "current_gdd": round(gdd_cum, 2), "ndre": ndre_data, "ndre_mean": ndre_mean, "weed_percentage": weed_percentage, "n_dose_kg_ha": n_dose}
