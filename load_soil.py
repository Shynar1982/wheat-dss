import pandas as pd
from sqlalchemy import create_engine
import os

# --- НАСТРОЙКА ПОДКЛЮЧЕНИЯ ---
DB_URL = 'sqlite:///agriculture.db' 

# ПРАВИЛЬНЫЙ ПУТЬ К ФАЙЛУ
csv_file = 'data/features/master_dataset.csv'

if not os.path.exists(csv_file):
    print(f"❌ Ошибка: Файл {csv_file} не найден.")
else:
    print("📖 Чтение CSV файла (это может занять пару минут, файл большой)...")
    cols = ['id', 'field_name', 'grid_id', 'ph', 'soc', 'no3', 'p', 'k']
    df = pd.read_csv(csv_file, usecols=cols)
    
    df = df.rename(columns={'id': 'field_id', 'p': 'p205', 'k': 'k20'})
    
    for col in ['ph', 'soc', 'no3', 'p205', 'k20']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    df = df.dropna(subset=['field_id'])
    
    print("💾 Подключение к базе данных и запись...")
    engine = create_engine(DB_URL)
    
    df.to_sql('soil_properties', engine, if_exists='replace', index=False)
    
    print(f"✅ Успешно! В таблицу 'soil_properties' записано {len(df)} строк.")