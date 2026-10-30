import asyncio
import pandas as pd
from sqlalchemy import text
from app.core.database import engine, Base
from app.services.yield_predictor import SoilProperty

async def main():
    print("📖 Чтение CSV файла...")
    csv_file = 'data/features/master_dataset.csv'
    cols = ['id', 'field_name', 'grid_id', 'ph', 'soc', 'no3', 'p', 'k']
    df = pd.read_csv(csv_file, usecols=cols)
    df = df.rename(columns={'id': 'field_id', 'p': 'p205', 'k': 'k20'})

    for col in ['ph', 'soc', 'no3', 'p205', 'k20']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna(subset=['field_id'])

    print("💾 Создание таблицы 'soil_properties' в PostgreSQL...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("📤 Загрузка данных...")
    async with engine.begin() as conn:
        # Преобразуем DataFrame в список кортежей для вставки
        records = df[['field_id', 'ph', 'soc', 'no3', 'p205', 'k20']].to_records(index=False)
        # Очищаем таблицу перед вставкой (на случай, если там что-то было)
        await conn.execute(text("TRUNCATE TABLE soil_properties"))
        # Вставляем данные пачками
        for record in records:
            await conn.execute(
                text("INSERT INTO soil_properties (field_id, ph, soc, no3, p205, k20) VALUES (:fid, :ph, :soc, :no3, :p, :k)"),
                {"fid": int(record[0]), "ph": float(record[1]), "soc": float(record[2]), "no3": float(record[3]), "p": float(record[4]), "k": float(record[5])}
            )

    print(f"✅ Успешно! В таблицу 'soil_properties' в PostgreSQL записано {len(df)} строк.")

if __name__ == "__main__":
    asyncio.run(main())
