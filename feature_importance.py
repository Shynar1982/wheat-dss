import joblib
import matplotlib.pyplot as plt
import pandas as pd

# 1. Загружаем нашу обученную модель
print("📖 Загрузка модели...")
model = joblib.load('yield_model_v3.pkl')

# 2. Названия признаков (в том же порядке, в котором мы их подавали в модель)
features = ['ph', 'soc', 'no3', 'p205', 'k20', 'ndvi', 'temp', 'precip']
# Переводим названия на русский для красивого графика
features_ru = ['pH (Кислотность)', 'SOC (Гумус)', 'NO3 (Азот)', 'P205 (Фосфор)', 
               'K20 (Калий)', 'NDVI (Вегетация)', 'Температура', 'Осадки']

# 3. Достаем важность признаков
importances = model.feature_importances_
indices = importances.argsort()[::-1] # Сортируем по убыванию

# 4. Строим график
plt.figure(figsize=(10, 6))
plt.title("Важность признаков в модели прогнозирования урожайности (Random Forest)", fontsize=14)
plt.bar(range(len(importances)), importances[indices], align="center", color='#228B22')
plt.xticks(range(len(importances)), [features_ru[i] for i in indices], rotation=45, ha='right', fontsize=11)
plt.ylabel("Вклад в прогноз (Feature Importance)", fontsize=12)
plt.tight_layout()

# 5. Сохраняем картинку
plt.savefig('feature_importance.png', dpi=300)
print("📊 График сохранен в файл 'feature_importance.png'")

# 6. Выводим цифры в консоль (для текста диссертации)
print("\n📈 Вклад признаков (в процентах):")
for i in indices:
    print(f" - {features_ru[i]}: {importances[i]*100:.1f}%")
