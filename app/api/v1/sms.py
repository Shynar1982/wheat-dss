from fastapi import APIRouter
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/fields", tags=["sms"])

@router.post("/{field_id}/send_sms")
async def send_sms_report(field_id: int):
    # Здесь в реальной системе был бы вызов Twilio/SMS.RU
    # Для демонстрации на защите мы просто имитируем успешную отправку
    logger.info(f"Имитация отправки СМС для поля {field_id}...")
    logger.info(f"Текст СМС: 'Внимание! По данным DSS для поля {field_id} достигнут порог GDD. Рекомендуется начать уборку. Урожайность прогнозируется на уровне 4.5 т/га.'")
    
    return {
        "status": "success", 
        "message": f"СМС-отчет по полю {field_id} успешно отправлен агроному (Имитация)"
    }
