import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

print("📖 Загрузка данных...")
csv_file = 'data/features/master_dataset.csv'
cols = ['ph', 'soc', 'no3', 'p', 'k', 's2_NDVI_summer', 'climate_MAT', 'climate_MAP']
df = pd.read_csv(csv_file, usecols=cols)
df = df.rename(columns={'p': 'p205', 'k': 'k20', 's2_NDVI_summer': 'ndvi', 'climate_MAT': 'temp', 'climate_MAP': 'precip'})
df = df.dropna()

np.random.seed(42)
df['yield_t_ha'] = (df['ndvi'] * 5.0 + df['soc'] * 0.3 + (df['precip'] / 100) * 0.8 - abs(df['temp'] - 15) * 0.1 + np.random.normal(0, 0.2, len(df))).clip(lower=0.5)

X = df[['ph', 'soc', 'no3', 'p205', 'k20', 'ndvi', 'temp', 'precip']]
y = df['yield_t_ha']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print("🧠 Обучение модели...")
model = RandomForestRegressor(n_estimators=150, max_depth=10, random_state=42)
model.fit(X_train, y_train)

predictions = model.predict(X_test)
mae = mean_absolute_error(y_test, predictions)
r2 = r2_score(y_test, predictions)

print(f"📊 МЕТРИКИ КАЧЕСТВА:")
print(f"   - MAE (ошибка): {mae:.2f} т/га")
print(f"   - R² (точность): {r2:.3f}")

joblib.dump(model, 'yield_model_v3.pkl')
print("💾 Модель сохранена!")
