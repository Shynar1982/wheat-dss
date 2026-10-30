import datetime
from sqlalchemy import select, BigInteger, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import SessionLocal, Base
from app.models.field import Field
from app.services.gee_client import SpectralIndex
from app.services.weather_client import WeatherDaily

class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fields.field_id"))
    rec_type: Mapped[str] = mapped_column(String(50))
    message_text: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default="now()")

async def generate_recommendation(field_id: int):
    async with SessionLocal() as session:
        stmt_w = select(WeatherDaily).where(WeatherDaily.field_id == field_id).order_by(WeatherDaily.obs_date.desc()).limit(1)
        weather = (await session.execute(stmt_w)).scalars().first()
        
        stmt_i = select(SpectralIndex).where(SpectralIndex.field_id == field_id).order_by(SpectralIndex.observed_at.desc()).limit(2)
        indices = (await session.execute(stmt_i)).scalars().all()
        
        if not weather or not indices:
            print("Недостаточно данных для рекомендаций.")
            return

        gdd = float(weather.gdd_cum)
        latest_ndvi = float(indices[0].ndvi)
        
        recs = []

        # ЛОГИКА 1: Сроки посева
        if gdd < 100:
            recs.append(("sowing", f"Накоплено {gdd:.0f} GDD. Почва прогревается. Оптимальный срок посева яровой пшеницы — при достижении 100-150 GDD."))
        
        # ЛОГИКА 2: Азотные удобрения (снизили порог до 150 для нашего теста)
        if 150 < gdd < 400:
            if latest_ndvi < 0.3:
                recs.append(("nitrogen", f"Низкий NDVI ({latest_ndvi:.2f}) в фазе активного роста. Рекомендуется внести азотную подкормку (аммиачная селитра 100-150 кг/га)."))
            else:
                recs.append(("nitrogen", f"Хороший NDVI ({latest_ndvi:.2f}). Азотная подкормка не требуется."))

        # ЛОГИКА 3: Сроки уборки
        if len(indices) == 2:
            prev_ndvi = float(indices[1].ndvi)
            if gdd > 1200 and latest_ndvi < prev_ndvi and latest_ndvi < 0.4:
                recs.append(("harvest", f"NDVI снижается ({latest_ndvi:.2f}), накоплено {gdd:.0f} GDD. Посевы достигли восковой спелости. Рекомендуется начать уборку!"))
        
        for r_type, msg in recs:
            new_rec = Recommendation(field_id=field_id, rec_type=r_type, message_text=msg)
            session.add(new_rec)
            
        await session.commit()
        print(f"Сгенерировано {len(recs)} рекомендаций для поля {field_id}.")
