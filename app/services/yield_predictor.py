import datetime
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy import select, func, BigInteger, Date, Numeric, String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import SessionLocal, Base
from app.services.gee_client import SpectralIndex
from app.services.weather_client import WeatherDaily

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
        # 1. АГРЕГАЦИЯ ПРИЗНАКОВ (Feature Engineering) для текущего года
        # Сумма осадков и средний NDVI за май
        stmt_w = select(func.sum(WeatherDaily.precip_mm)).where(WeatherDaily.field_id == field_id)
        total_precip = (await session.execute(stmt_w)).scalar() or 0.0
        
        stmt_n = select(func.avg(SpectralIndex.ndvi)).where(SpectralIndex.field_id == field_id)
        avg_ndvi = (await session.execute(stmt_n)).scalar() or 0.0

        print(f"Текущие признаки для прогноза: Осадки={total_precip:.1f}мм, NDVI={avg_ndvi:.2f}")

        # 2. ПОДГОТОВКА ОБУЧАЮЩЕЙ ВЫБОРКИ
        # Так как реальной истории нет, сгенерируем синтетические данные для примера
        # (В диссертации здесь будет загрузка из Бюро нац. статистики)
        X_train = pd.DataFrame({
            'precip': [40.5, 55.2, 30.1, 80.5, 25.0, 60.3],
            'ndvi': [0.35, 0.55, 0.25, 0.65, 0.20, 0.50]
        })
        y_train = np.array([1.5, 2.8, 1.1, 3.2, 0.9, 2.5]) # Урожайность т/га

        # 3. ОБУЧЕНИЕ МОДЕЛИ (Случайный лес)
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)

        # 4. ПРОГНОЗ ДЛЯ НАШЕГО ПОЛЯ
        X_test = pd.DataFrame({'precip': [total_precip], 'ndvi': [avg_ndvi]})
        predicted_yield = model.predict(X_test)[0]

        # Округляем и убираем отрицательные значения
        predicted_yield = max(0.0, round(float(predicted_yield), 3))

        # 5. СОХРАНЯЕМ РЕЗУЛЬТАТ
        new_pred = YieldPrediction(
            field_id=field_id,
            predicted_yield_t_ha=predicted_yield,
            model_version="RandomForest_v1"
        )
        session.add(new_pred)
        await session.commit()
        
        print(f"УСПЕХ! Прогноз урожайности для поля {field_id}: {predicted_yield} т/га")
