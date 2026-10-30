import datetime
import pandas as pd
import numpy as np
import joblib
import os
from sqlalchemy import select, func, BigInteger, Date, Numeric, String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import SessionLocal, Base
from app.services.gee_client import SpectralIndex
from app.services.weather_client import WeatherDaily

class SoilProperty(Base):
    __tablename__ = "soil_properties"
    field_id: Mapped[int] = mapped_column(BigInteger, primary_key=True) 
    ph: Mapped[float] = mapped_column(Numeric(5, 2))
    soc: Mapped[float] = mapped_column(Numeric(5, 2))
    no3: Mapped[float] = mapped_column(Numeric(6, 2))
    p205: Mapped[float] = mapped_column(Numeric(6, 2))
    k20: Mapped[float] = mapped_column(Numeric(6, 2))

class YieldPrediction(Base):
    __tablename__ = "yield_predictions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fields.field_id"))
    prediction_date: Mapped[datetime.date] = mapped_column(Date, server_default="now()")
    predicted_yield_t_ha: Mapped[float] = mapped_column(Numeric(6, 3))
    model_version: Mapped[str] = mapped_column(String(50))

# Загружаем модель один раз при старте сервера
MODEL_PATH = 'yield_model_v3.pkl'
if os.path.exists(MODEL_PATH):
    model = joblib.load(MODEL_PATH)
else:
    model = None
    print("⚠️ ВНИМАНИЕ: Модель не найдена. Запустите train_model.py")

async def train_and_predict(field_id: int):
    if model is None:
        raise ValueError("Модель не загружена. Сначала обучите её.")
        
    async with SessionLocal() as session:
        # Собираем данные для прогноза
        stmt_w = select(func.sum(WeatherDaily.precip_mm)).where(WeatherDaily.field_id == field_id)
        total_precip = (await session.execute(stmt_w)).scalar() or 0.0
        
        stmt_n = select(func.avg(SpectralIndex.ndvi)).where(SpectralIndex.field_id == field_id)
        avg_ndvi = (await session.execute(stmt_n)).scalar() or 0.0

        stmt_s = select(
            func.avg(SoilProperty.ph), func.avg(SoilProperty.soc),
            func.avg(SoilProperty.no3), func.avg(SoilProperty.p205), func.avg(SoilProperty.k20)
        ).where(SoilProperty.field_id == field_id)
        soil_data = (await session.execute(stmt_s)).first()
        
        if soil_data and soil_data[0] is not None:
            ph, soc, no3, p205, k20 = [float(x) for x in soil_data]
        else:
            ph, soc, no3, p205, k20 = 7.0, 2.5, 5.0, 20.0, 500.0

        # Для температуры и осадков берем средние значения из климатических данных, 
        # так как у нас нет прямого API для текущей температуры в этом скрипте
        temp = 14.4 # среднее по датасету
        precip = total_precip if total_precip > 0 else 250.0

        # Прогноз (порядок колонок ДОЛЖЕН совпадать с обучением: 
        # ph, soc, no3, p205, k20, ndvi, temp, precip)
        X_test = pd.DataFrame({
            'ph': [ph], 'soc': [soc], 'no3': [no3], 'p205': [p205], 'k20': [k20],
            'ndvi': [avg_ndvi if avg_ndvi > 0 else 0.4], 
            'temp': [temp], 'precip': [precip]
        })
        
        predicted_yield = model.predict(X_test)[0]
        predicted_yield = max(0.0, round(float(predicted_yield), 3))

        # Сохраняем результат
        new_pred = YieldPrediction(
            field_id=field_id,
            predicted_yield_t_ha=predicted_yield,
            model_version="RandomForest_v3_Dissertation"
        )
        session.add(new_pred)
        await session.commit()
        
        print(f"✅ УСПЕХ! Прогноз для поля {field_id}: {predicted_yield} т/га (Модель v3)")
        return predicted_yield
