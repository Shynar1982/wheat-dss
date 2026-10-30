from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.services.yield_predictor import YieldPrediction, train_and_predict

router = APIRouter(prefix="/v1/fields", tags=["yield"])

# 1. Этот эндпоинт мы уже имели - он показывает историю прогнозов
@router.get("/{field_id}/yield/predictions")
async def get_predictions(field_id: int, db: AsyncSession = Depends(get_session)):
    stmt = select(YieldPrediction).where(YieldPrediction.field_id == field_id).order_by(YieldPrediction.id.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

# 2. НОВЫЙ ЭНДПОИНТ - запускает модель и делает новый прогноз
@router.post("/{field_id}/yield/predict")
async def run_prediction(field_id: int):
    try:
        # Вызываем нашу функцию из yield_predictor.py
        await train_and_predict(field_id)
        return {
            "status": "success", 
            "message": f"Прогноз для поля {field_id} успешно рассчитан и сохранен в базу."
        }
    except Exception as e:
        # Если произойдет ошибка (например, поля нет в базе), API вернет 500 ошибку с текстом
        raise HTTPException(status_code=500, detail=str(e))