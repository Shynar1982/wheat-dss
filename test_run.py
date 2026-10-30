import asyncio
from app.core.database import SessionLocal
from app.services.yield_predictor import train_and_predict
from sqlalchemy import text

async def main():
    field_id = 130
    
    print("🛠 Подготовка тестового поля в базе данных (с полигоном)...")
    async with SessionLocal() as session:
        try:
            # Создаем полигон (прямоугольник) через PostGIS ST_GeomFromText
            # Координаты 4326 (WGS84) взяты из вашего датасета
            await session.execute(
                text("""
                    INSERT INTO fields (field_id, name, geom) 
                    VALUES (
                        :fid, 
                        'Тестовое поле', 
                        ST_GeomFromText('POLYGON((60.64 52.07, 60.65 52.07, 60.65 52.08, 60.64 52.08, 60.64 52.07))', 4326)
                    ) 
                    ON CONFLICT (field_id) DO NOTHING
                """),
                {"fid": field_id}
            )
            await session.commit()
            print("✅ Поле с геометрией успешно добавлено.")
        except Exception as e:
            print(f"⚠️ Ошибка при создании поля: {e}")
            await session.rollback()

    print(f"🚀 Запуск прогноза для поля {field_id}...")
    await train_and_predict(field_id)

if __name__ == "__main__":
    asyncio.run(main())
