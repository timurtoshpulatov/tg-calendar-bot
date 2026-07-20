"""
Точка входа — запускает Telegram-бота-календарь с ИИ-парсингом задач.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import (
    BOT_TOKEN, AI_API_KEY, AI_MODEL, AI_BASE_URL, AI_MAX_TOKENS,
    DIGEST_TIME, DB_PATH
)
from database import Database
from ai_parser import TaskParser
from scheduler import ReminderScheduler
from handlers import router, setup as setup_handlers

logging.basicConfig(level=logging.INFO)


async def main():
    # Инициализация бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )

    # Показываем @username бота в логах при старте
    me = await bot.get_me()
    print(f"🚀 Запуск бота-календаря @{me.username}...")
    print(f"   Модель ИИ: {AI_MODEL}")

    dp = Dispatcher()
    db = Database(DB_PATH)
    parser = TaskParser(
        api_key=AI_API_KEY,
        model=AI_MODEL,
        base_url=AI_BASE_URL,
        max_tokens=AI_MAX_TOKENS,
    )

    # Подключаем обработчики
    setup_handlers(db, parser)
    dp.include_router(router)

    # Запускаем планировщик напоминаний
    scheduler = ReminderScheduler(bot, db, digest_time=DIGEST_TIME)
    asyncio.create_task(scheduler.start())

    print("✅ Бот запущен! Жду сообщения...")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
