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
    weather_data = []
    gdd_data = []
    gdd_cum = 0
    base_temp = 5.0
    sowing_date_obj = datetime.date(start_date.year, 5, 10)
    current_date = start_date
    
    while current_date <= end_date:
        day_of_year = current_date.timetuple().tm_yday
        t_max = 20 + 12 * math.sin(2 * math.pi * (day_of_year - 130) / 365) 
        t_min = t_max - 10 - random.uniform(0, 5)
        precip = random.uniform(0, 4) if random.random() > 0.75 else 0.0
        
        if current_date >= sowing_date_obj:
            avg_temp = (t_max + t_min) / 2
            if avg_temp > base_temp:
                gdd_cum += (avg_temp - base_temp)
                
        date_str = current_date.strftime("%Y-%m-%d")
        weather_data.append({"obs_date": date_str, "t_max_c": round(t_max, 1), "t_min_c": round(t_min, 1), "precip_mm": round(precip, 1)})
        gdd_data.append({"obs_date": date_str, "gdd_cum": round(gdd_cum, 2)})
        current_date += datetime.timedelta(days=1)
        
    return weather_data, gdd_data, sowing_date_obj.strftime("%Y-%m-%d")

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
    start_date_obj = datetime.date(2024, 3, 1)
    end_date_obj = datetime.date(2024, 10, 1)
    
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date_obj}&end_date={end_date_obj}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
    headers = {"User-Agent": "WheatDSS/1.0"}
    
    weather_list, gdd_list, sowing_date, gdd_cum = [], [], None, 0
    base_temp = 5.0 
    api_success = False
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                daily = response.json().get("daily", {})
                if daily and daily.get("time"):
                    for i in range(len(daily["time"])):
                        t_max, t_min = daily["temperature_2m_max"][i], daily["temperature_2m_min"][i]
                        precip, current_date_str = daily["precipitation_sum"][i], daily["time"][i]
                        
                        if t_max is not None and t_min is not None:
                            avg_temp = (t_max + t_min) / 2
                            if current_date_str[5:7] in ['03', '04', '05'] and avg_temp >= 10.0 and sowing_date is None:
                                sowing_date = current_date_str
                                
                        if sowing_date and current_date_str >= sowing_date:
                            if t_max is not None and t_min is not None:
                                gdd_cum += max(0, ((t_max + t_min) / 2) - base_temp)
                                
                        weather_list.append({"obs_date": current_date_str, "t_max_c": t_max or 0, "t_min_c": t_min or 0, "precip_mm": precip or 0})
                        gdd_list.append({"obs_date": current_date_str, "gdd_cum": round(gdd_cum, 2)})
                    api_success = True
    except Exception:
        pass

    if not api_success or not weather_list:
        weather_list, gdd_list, sowing_date = generate_mock_weather(start_date_obj, end_date_obj)
        gdd_cum = gdd_list[-1]["gdd_cum"] if gdd_list else 0

    return {
        "current_month": current_month, "sowing_date": sowing_date,
        "current_gdd": round(gdd_cum, 2), "weather_data": weather_list, "gdd_data": gdd_list
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

@router.get("/api/fields/{field_id}/agro_forecast")
async def get_agro_forecast(field_id: int, sim_month: int = Query(0), db: AsyncSession = Depends(get_session)):
    # 1. Получаем площадь поля
    stmt = select(Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    area_ha = result.scalar() or 20.0

    current_month = sim_month if sim_month != 0 else datetime.datetime.now().month
    today = datetime.date(2024, current_month, 15) if current_month != 0 else datetime.date.today()

    SOWING_RATE = 50.0  # га/день
    HARVEST_RATE = 15.0 # га/день
    
    sowing_days = math.ceil(area_ha / SOWING_RATE)
    harvest_days = math.ceil(area_ha / HARVEST_RATE)
    result_data = {}

    # Логика посева
    sowing_start, sowing_end = datetime.date(2024, 5, 10), datetime.date(2024, 5, 25)
    if today > sowing_end:
        result_data["sowing"] = {"status": "missed", "message": "Посевное окно завершено.", "details": ""}
    elif today < sowing_start:
        result_data["sowing"] = {"status": "early", "message": f"До посева {(sowing_start - today).days} дней.", "details": f"Ожидаемая продолжительность сева: {sowing_days} дн. (площадь {area_ha:.1f} га)"}
    else:
        best_sowing_day = today + datetime.timedelta(days=2)
        if best_sowing_day > sowing_end: best_sowing_day = sowing_end
        end_sowing_date = best_sowing_day + datetime.timedelta(days=sowing_days)
        
        if end_sowing_date <= sowing_end:
            result_data["sowing"] = {"status": "success", "message": f"Успеваем! Начало сева: {best_sowing_day.strftime('%d.%m')}.", "details": f"Площадь {area_ha:.1f} га. Сев займет {sowing_days} дн. Завершение: {end_sowing_date.strftime('%d.%m')}."}
        else:
            result_data["sowing"] = {"status": "risk", "message": f"Риск! Начало сева: {best_sowing_day.strftime('%d.%m')}.", "details": f"Площадь {area_ha:.1f} га. Сев займет {sowing_days} дн. Завершение {end_sowing_date.strftime('%d.%m')} выходит за пределы (25.05)!"}

    # Логика уборки
    harvest_start, harvest_end = datetime.date(2024, 8, 10), datetime.date(2024, 9, 20)
    if today < harvest_start:
        result_data["harvest"] = {"status": "early", "message": "Уборка еще не началась.", "details": f"Ожидаемая продолжительность: {harvest_days} дн. (площадь {area_ha:.1f} га)"}
    elif today > harvest_end:
        result_data["harvest"] = {"status": "missed", "message": "Уборочная кампания завершена.", "details": ""}
    else:
        best_harvest_day = today + datetime.timedelta(days=1)
        if best_harvest_day > harvest_end: best_harvest_day = harvest_end
        end_harvest_date = best_harvest_day + datetime.timedelta(days=harvest_days)
        
        if end_harvest_date <= harvest_end:
            result_data["harvest"] = {"status": "success", "message": f"Успеваем! Начало уборки: {best_harvest_day.strftime('%d.%m')}.", "details": f"Площадь {area_ha:.1f} га. Уборка займет {harvest_days} дн. Завершение: {end_harvest_date.strftime('%d.%m')}."}
        else:
            result_data["harvest"] = {"status": "risk", "message": f"Риск! Начало уборки: {best_harvest_day.strftime('%d.%m')}.", "details": f"Площадь {area_ha:.1f} га. Уборка займет {harvest_days} дн. Завершение {end_harvest_date.strftime('%d.%m')} выходит за пределы (20.09)!"}

    return result_data

@router.get("/api/fields/{field_id}/fertilizer")
async def get_fertilizer_recommendation(
    field_id: int,
    sim_month: int = Query(0),
    db: AsyncSession = Depends(get_session)
):
    # 1. Получаем площадь и прогноз урожайности
    stmt = select(Field.area_ha).where(Field.field_id == field_id)
    result = await db.execute(stmt)
    area_ha = result.scalar() or 20.0

    # Получаем последний прогноз урожайности (для расчета выноса)
    stmt_yield = select(YieldPrediction.predicted_yield_t_ha).where(YieldPrediction.field_id == field_id).order_by(YieldPrediction.prediction_date.desc()).limit(1)
    result_yield = await db.execute(stmt_yield)
    predicted_yield_t_ha = result_yield.scalar() or 2.0 # По умолчанию 2 т/га, если прогноза нет

    # 2. Получаем NDVI для корректировки дозы
    stmt_ndvi = select(FieldNDVI.ndvi).where(FieldNDVI.field_id == field_id).order_by(FieldNDVI.observed_at.desc()).limit(1)
    result_ndvi = await db.execute(stmt_ndvi)
    ndvi = result_ndvi.scalar() or 0.4

    # 3. Определяем текущий месяц
    month = sim_month if sim_month != 0 else datetime.datetime.now().month

    # 4. Зимой не удобряем
    if month >= 11 or month <= 2:
        return {
            "status": "winter",
            "message": "Зимний период: внесение удобрений не требуется.",
            "recommendations": [],
            "total_kg": 0
        }

    # 5. Расчет выноса питательных веществ на планируемую урожайность
    # Нормы выноса на 1 т зерна (с учетом соломы): N: 24-30, P2O5: 10-13, K2O: 16-25
    n_norm_per_t = 27 # среднее значение
    p_norm_per_t = 11.5
    k_norm_per_t = 20.5
    
    total_n_need = predicted_yield_t_ha * n_norm_per_t
    total_p_need = predicted_yield_t_ha * p_norm_per_t
    total_k_need = predicted_yield_t_ha * k_norm_per_t

    # 6. Формируем рекомендации по фазам
    recommendations = []
    
    # Фосфор и калий: все в предпосевное внесение
    if total_p_need > 0:
        recommendations.append({
            "phase": "Предпосевное (основное)",
            "nutrient": "Фосфор (P₂O₅)",
            "dose_kg_ha": round(total_p_need / area_ha, 1),
            "total_kg": round(total_p_need, 1),
            "note": "Вносится под предпосевную культивацию."
        })
    if total_k_need > 0:
        recommendations.append({
            "phase": "Предпосевное (основное)",
            "nutrient": "Калий (K₂O)",
            "dose_kg_ha": round(total_k_need / area_ha, 1),
            "total_kg": round(total_k_need, 1),
            "note": "Вносится под предпосевную культивацию."
        })

    # Азот: дробное внесение
    # 60% - предпосевное, 40% - подкормка в кущение/трубкование
    n_pre_sowing = total_n_need * 0.6
    n_top_dressing_base = total_n_need * 0.4

    # Корректировка подкормки по NDVI
    if ndvi < 0.3:
        ndvi_factor = 1.2 # Дефицит азота, увеличиваем дозу на 20%
        ndvi_note = "Низкий NDVI (<0.3): повышенная потребность в азоте."
    elif ndvi < 0.5:
        ndvi_factor = 1.0 # Норма
        ndvi_note = "Средний NDVI (0.3-0.5): стандартная доза."
    else:
        ndvi_factor = 0.7 # Достаточно азота, снижаем дозу
        ndvi_note = "Высокий NDVI (>0.5): растения хорошо обеспечены азотом."

    n_top_dressing_actual = n_top_dressing_base * ndvi_factor

    recommendations.append({
        "phase": "Предпосевное (основное)",
        "nutrient": "Азот (N)",
        "dose_kg_ha": round(n_pre_sowing / area_ha, 1),
        "total_kg": round(n_pre_sowing, 1),
        "note": "60% от общей потребности. Вносится весной под предпосевную культивацию."
    })

    if n_top_dressing_actual > 0:
        recommendations.append({
            "phase": "Подкормка (фаза кущения/трубкования)",
            "nutrient": "Азот (N)",
            "dose_kg_ha": round(n_top_dressing_actual / area_ha, 1),
            "total_kg": round(n_top_dressing_actual, 1),
            "note": f"40% от общей потребности, скорректированные по NDVI. {ndvi_note}"
        })

    # 7. Формируем общее сообщение
    total_fert_kg = round(n_pre_sowing + n_top_dressing_actual + total_p_need + total_k_need, 1)
    message = f"Планируемая урожайность: {predicted_yield_t_ha:.1f} т/га. Общая потребность в удобрениях: {total_fert_kg} кг."

    return {
        "status": "success",
        "message": message,
        "ndvi": ndvi,
        "predicted_yield": predicted_yield_t_ha,
        "recommendations": recommendations,
        "total_kg": total_fert_kg
    }
