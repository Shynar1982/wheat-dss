import asyncio
import pandas as pd
from sqlalchemy import text
from app.core.database import engine

async def main():
    print("📖 Загрузка данных о полях из CSV...")
    csv_file = 'data/features/master_dataset.csv'
    # Берем id, название поля и координаты (WKT)
    df = pd.read_csv(csv_file, usecols=['id', 'field_name', 'geometry_wkt'])
    
    # Убираем дубликаты по id (так как одно поле может состоять из нескольких grid_id)
    df = df.drop_duplicates(subset=['id'])
    # Убираем строки, где нет геометрии (иначе база данных выдаст ошибку)
    df = df.dropna(subset=['geometry_wkt'])
    
    print(f"Найдено {len(df)} уникальных полей. Запись в базу данных...")
    
    async with engine.begin() as conn:
        for index, row in df.iterrows():
            try:
                # Используем ST_GeomFromText для преобразования текста в геометрию PostGIS
                await conn.execute(
                    text("""
                        INSERT INTO fields (field_id, name, geom) 
                        VALUES (:fid, :name, ST_GeomFromText(:wkt, 4326)) 
                        ON CONFLICT (field_id) DO NOTHING
                    """),
                    {"fid": int(row['id']), "name": str(row['field_name']), "wkt": str(row['geometry_wkt'])}
                )
            except Exception as e:
                # Если какое-то поле не влезет, скрипт продолжит работу
                pass
    
    print("✅ Все поля успешно добавлены в базу данных!")

if __name__ == "__main__":
    asyncio.run(main())
