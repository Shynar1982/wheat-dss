import datetime
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy import select, func, BigInteger, Date, Numeric, String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import SessionLocal, Base
from app.services.gee_client import SpectralIndex
from app.services.weather_client import WeatherDaily

# --- 1. ДОБАВЛЯЕМ МОДЕЛЬ ДЛЯ ПОЧВЕННЫХ ДАННЫХ ---
class SoilProperty(Base):
    __tablename__ = "soil_properties"
    # В нашей таблице soil_properties колонка field_id может повторяться (если у поля несколько grid_id)
    # Поэтому мы не делаем её primary_key, а просто мапим
    field_id: Mapped[int] = mapped_column(BigInteger, primary_key=True) 
    ph: Mapped[float] = mapped_column(Numeric(5, 2))
    soc: Mapped[float] = mapped_column(Numeric(5, 2))
    no3: Mapped[float] = mapped_column(Numeric(6, 2))
    p205: Mapped[float] = mapped_column(Numeric(6, 2))
    k20: Mapped[float] = mapped_column(Numeric(6, 2))

class HistoricalYield(Base):
    __tablename__ = "historical_yield"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fields.field_id"))
    year: Mapped[int] = mapped_column(Integer)
    yield_t_ha: Mapped[float] = mapped_column(Numeric(6, 3))

class YieldPrediction(Base):
    __tablename__ = "yield_predictions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fields.field_id"))
    prediction_date: Mapped[datetime.date] = mapped_column(Date, server_default="now()")
    predicted_yield_t_ha: Mapped[float] = mapped_column(Numeric(6, 3))
    model_version: Mapped[str] = mapped_column(String(50))

async def train_and_predict(field_id: int):
    async with SessionLocal() as session:
        # --- 2. СБОР ВСЕХ ПРИЗНАКОВ ДЛЯ ТЕКУЩЕГО ГОДА ---
        # Осадки
        stmt_w = select(func.sum(WeatherDaily.precip_mm)).where(WeatherDaily.field_id == field_id)
        total_precip = (await session.execute(stmt_w)).scalar() or 0.0
        
        # NDVI
        stmt_n = select(func.avg(SpectralIndex.ndvi)).where(SpectralIndex.field_id == field_id)
        avg_ndvi = (await session.execute(stmt_n)).scalar() or 0.0

        # ПОЧВЕННЫЕ ДАННЫЕ (берем среднее, если для поля есть несколько записей)
        stmt_s = select(
            func.avg(SoilProperty.ph),
            func.avg(SoilProperty.soc),
            func.avg(SoilProperty.no3),
            func.avg(SoilProperty.p205),
            func.avg(SoilProperty.k20)
        ).where(SoilProperty.field_id == field_id)
        
        soil_data = (await session.execute(stmt_s)).first()
        
        # Если данных по почве нет, ставим средние заглушки (или 0)
        if soil_data and soil_data[0] is not None:
            ph, soc, no3, p205, k20 = [float(x) for x in soil_data]
        else:
            print(f"⚠️ Внимание: Нет почвенных данных для поля {field_id}. Используются средние значения.")
            ph, soc, no3, p205, k20 = 7.0, 2.5, 5.0, 20.0, 500.0

        print(f"Текущие признаки: Осадки={total_precip:.1f}мм, NDVI={avg_ndvi:.2f}, pH={ph:.1f}, SOC={soc:.1f}")

        # --- 3. ПОДГОТОВКА ОБУЧАЮЩЕЙ ВЫБОРКИ ---
        # Обновляем синтетические данные: теперь добавили почвенные признаки
        X_train = pd.DataFrame({
            'precip': [40.5, 55.2, 30.1, 80.5, 25.0, 60.3],
            'ndvi': [0.35, 0.55, 0.25, 0.65, 0.20, 0.50],
            'ph': [6.8, 7.1, 6.5, 7.4, 6.2, 7.0],
            'soc': [2.1, 3.2, 1.8, 3.8, 1.5, 2.9],
            'no3': [4.5, 6.8, 3.2, 8.1, 2.8, 5.9],
            'p205': [18.0, 25.0, 12.0, 32.0, 10.0, 22.0],
            'k20': [480.0, 610.0, 400.0, 720.0, 350.0, 550.0]
        })
        y_train = np.array([1.5, 2.8, 1.1, 3.2, 0.9, 2.5])

        # --- 4. ОБУЧЕНИЕ МОДЕЛИ ---
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)

        # --- 5. ПРОГНОЗ ДЛЯ НАШЕГО ПОЛЯ ---
        # Внимание: порядок колонок в X_test должен совпадать с X_train!
        X_test = pd.DataFrame({
            'precip': [total_precip],
            'ndvi': [avg_ndvi],
            'ph': [ph],
            'soc': [soc],
            'no3': [no3],
            'p205': [p205],
            'k20': [k20]
        })
        
        predicted_yield = model.predict(X_test)[0]
        predicted_yield = max(0.0, round(float(predicted_yield), 3))

        # --- 6. СОХРАНЯЕМ РЕЗУЛЬТАТ ---
        new_pred = YieldPrediction(
            field_id=field_id,
            predicted_yield_t_ha=predicted_yield,
            model_version="RandomForest_v2_with_soil"
        )
        session.add(new_pred)
        await session.commit()
        
        print(f"✅ УСПЕХ! Прогноз урожайности для поля {field_id}: {predicted_yield} т/га")