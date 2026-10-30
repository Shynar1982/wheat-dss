import asyncio
import pandas as pd
from sqlalchemy import text
from app.core.database import engine

async def main():
    print("📥 Сбор данных из базы...")
    async with engine.connect() as conn:
        # Пишем SQL-запрос: объединяем поля, прогнозы и почвенные данные
        # Используем AVG для почвы, так как на одном поле может быть несколько grid_id
        query = text("""
            SELECT 
                f.field_id, 
                f.name as field_name,
                y.predicted_yield_t_ha,
                y.model_version,
                y.prediction_date,
                ROUND(AVG(s.ph), 2) as ph,
                ROUND(AVG(s.soc), 2) as soc,
                ROUND(AVG(s.no3), 2) as no3,
                ROUND(AVG(s.p205), 2) as p205,
                ROUND(AVG(s.k20), 2) as k20
            FROM fields f
            JOIN yield_predictions y ON f.field_id = y.field_id
            LEFT JOIN soil_properties s ON f.field_id = s.field_id
            GROUP BY f.field_id, f.name, y.predicted_yield_t_ha, y.model_version, y.prediction_date
            ORDER BY f.field_id;
        """)
        
        result = await conn.execute(query)
        columns = result.keys()
        rows = result.fetchall()
        
    print(f"📊 Получено {len(rows)} записей. Формирование Excel-файла...")
    
    # Превращаем в таблицу Pandas
    df = pd.DataFrame(rows, columns=columns)
    
    # Переименовываем колонки на русский для диссертации
    df.columns = ['ID Поля', 'Название поля', 'Прогноз (т/га)', 'Версия модели', 
                  'Дата прогноза', 'pH', 'SOC (Гумус)', 'NO3 (Азот)', 
                  'P205 (Фосфор)', 'K20 (Калий)']
    
    # Сохраняем в файл
    file_name = 'yield_predictions_report.xlsx'
    df.to_excel(file_name, index=False)
    print(f"✅ ГОТОВО! Все данные сохранены в файл: {file_name}")

if __name__ == "__main__":
    asyncio.run(main())
