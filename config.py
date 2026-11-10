import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CHAT_ID = os.getenv("CHAT_ID")
DAILY_SUMMARY_TIME = os.getenv("DAILY_SUMMARY_TIME", "21:00")
