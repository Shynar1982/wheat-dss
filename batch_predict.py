import asyncio
from sqlalchemy import select
from app.core.database import SessionLocal
from app.services.yield_predictor import train_and_predict, SoilProperty

async def main():
    print("📥 Получение списка всех полей из базы данных...")
    async with SessionLocal() as session:
        stmt = select(SoilProperty.field_id).distinct()
        result = await session.execute(stmt)
        field_ids = result.scalars().all()

    print(f"Найдено {len(field_ids)} полей. Запуск массового прогноза...")
    print("Пожалуйста, подождите, это может занять пару минут...")

    success_count = 0
    for fid in field_ids:
        try:
            await train_and_predict(fid) 
            success_count += 1
        except Exception:
            pass
    
    print(f"\n✅ ГОТОВО! Успешно рассчитан прогноз для {success_count} из {len(field_ids)} полей.")

if __name__ == "__main__":
    asyncio.run(main())
