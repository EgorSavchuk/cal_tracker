import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from loguru import logger

from config import TELEGRAM_BOT_TOKEN

bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Logging
logger.remove()
log = logger
log.add(sys.stdout, level="INFO")
log.add(
    "logs/ERROR/{time:YYYY-MM-DD}.log",
    level="ERROR",
    rotation="10 MB",
    compression="zip",
)
log.add(
    "logs/INFO/{time:YYYY-MM-DD}.log",
    level="INFO",
    rotation="10 MB",
    compression="zip",
)
log.info("Loader initialized")

dp.callback_query.middleware(CallbackAnswerMiddleware())
