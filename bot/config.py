import os

import dotenv

dotenv.load_dotenv()

DEBUG = os.getenv("DEBUG", "False").strip() == "True"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-20250514")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", os.getenv("ALLOWED_USER_ID", "0")))
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL", "")
