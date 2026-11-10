import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
import analysis
from handlers import router
from config import BOT_TOKEN, CHAT_ID, DAILY_SUMMARY_TIME

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)


async def send_daily_analysis():
    sessions = await db.get_today_sessions(int(CHAT_ID))
    if not sessions:
        await bot.send_message(CHAT_ID, "📊 Итоги дня: сегодня не было сессий.")
        return

    await bot.send_message(CHAT_ID, "⏳ Анализирую день...")
    result = analysis.analyze_day(sessions)
    await bot.send_message(CHAT_ID, f"📊 *Итоги дня:*\n\n{result}", parse_mode="Markdown")


async def main():
    await db.init_db()

    hour, minute = map(int, DAILY_SUMMARY_TIME.split(":"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_daily_analysis, "cron", hour=hour, minute=minute)
    scheduler.start()

    logging.info("Бот запущен. Анализ дня в %s", DAILY_SUMMARY_TIME)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
