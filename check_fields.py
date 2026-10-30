import asyncio
from sqlalchemy import text
from app.core.database import engine

async def main():
    async with engine.connect() as conn:
        print("Структура таблицы fields:")
        result = await conn.execute(text("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'fields';"))
        # Убрали await перед fetchall
        for row in result:
            print(f"- {row[0]} ({row[1]}), nullable: {row[2]}")

if __name__ == "__main__":
    asyncio.run(main())
