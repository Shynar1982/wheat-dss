import random
import datetime

async def send_sms(phone_number: str, message: str) -> bool:
    """
    Имитация отправки SMS. В будущем здесь будет подключение к Twilio или
    казахстанскому SMS-шлюзу.
    """
    # Имитируем задержку сети
    print(f"\n--- ОТПРАВКА SMS ---")
    print(f"Кому: {phone_number}")
    print(f"Текст: {message}")
    
    # Имитируем успешную отправку (99% успеха)
    success = random.random() > 0.01
    
    if success:
        print(f"Статус: Доставлено (SMS ID: {random.randint(100000, 999999)})")
        print(f"--------------------\n")
        return True
    else:
        print(f"Статус: Ошибка сети\n")
        return False
