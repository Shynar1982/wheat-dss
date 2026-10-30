import httpx
import datetime
from sqlalchemy import select, BigInteger, Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2.functions import ST_X, ST_Y, ST_Centroid
from app.models.field import Field
from app.core.database import SessionLocal, Base

class WeatherDaily(Base):
    __tablename__ = "weather_daily"
    field_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    obs_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    t_min_c: Mapped[float] = mapped_column(Numeric(5, 2))
    t_max_c: Mapped[float] = mapped_column(Numeric(5, 2))
    precip_mm: Mapped[float] = mapped_column(Numeric(6, 2))
    gdd_cum: Mapped[float] = mapped_column(Numeric(8, 2))

async def fetch_weather_for_field(field_id: int, start_date: str, end_date: str):
    async with SessionLocal() as session:
        # Получаем координаты центра поля (широта и долгота)
        stmt = select(ST_Y(ST_Centroid(Field.geom)), ST_X(ST_Centroid(Field.geom))).where(Field.field_id == field_id)
        row = (await session.execute(stmt)).first()
        if not row:
            print(f"Поле {field_id} не найдено")
            return
        
        lat, lon = row
        
        # Запрос к Open-Meteo (исторические данные)
        url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={start_date}&end_date={end_date}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code != 200:
                print(f"Ошибка API погоды: {response.text}")
                return
            
            data = response.json().get("daily", {})
            dates = data.get("time", [])
            t_maxs = data.get("temperature_2m_max", [])
            t_mins = data.get("temperature_2m_min", [])
            precips = data.get("precipitation_sum", [])
            
            added_count = 0
            gdd_cum = 0.0
            
            for i in range(len(dates)):
                dt = datetime.datetime.strptime(dates[i], '%Y-%m-%d').date()
                t_max = t_maxs[i] or 0.0
                t_min = t_mins[i] or 0.0
                precip = precips[i] or 0.0
                
                # Считаем GDD (базовая температура для пшеницы 5°C)
                daily_gdd = max(((t_max + t_min) / 2.0) - 5.0, 0.0)
                gdd_cum += daily_gdd
                
                record = WeatherDaily(
                    field_id=field_id, obs_date=dt, t_min_c=t_min, 
                    t_max_c=t_max, precip_mm=precip, gdd_cum=gdd_cum
                )
                session.add(record)
                added_count += 1
                
            await session.commit()
            print(f"Успешно добавлено {added_count} дней погоды для поля {field_id}!")
