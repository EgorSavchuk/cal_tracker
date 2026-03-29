from aiogram import Bot
from aiogram import Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from loguru import logger
from redis.asyncio.client import Redis

from config import TOKEN_BOT, REDIS_URL, PROJECT_NAME
from services.middleware import (
    UserRequestLoggingMiddleware,
    BotRequestLoggingMiddleware,
)

redis = Redis.from_url(REDIS_URL)

bot = Bot(token=TOKEN_BOT, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = RedisStorage(redis, key_builder=DefaultKeyBuilder(prefix=PROJECT_NAME))
dp = Dispatcher(storage=storage)


logger.remove()
log = logger
log.add(
    "logs/CRITICAL/{time:YYYY-MM-DD_HH-mm-ss}.log",
    level="CRITICAL",
    rotation="10 MB",
    compression="zip",
)
log.add(
    "logs/ERROR/{time:YYYY-MM-DD_HH-mm-ss}.log",
    level="ERROR",
    rotation="10 MB",
    compression="zip",
)
log.add(
    "logs/INFO/{time:YYYY-MM-DD_HH-mm-ss}.log",
    level="INFO",
    rotation="10 MB",
    compression="zip",
)
log.info("Start")

user_request_logger = UserRequestLoggingMiddleware()
bot_request_logger = BotRequestLoggingMiddleware()

dp.callback_query.middleware(CallbackAnswerMiddleware())
dp.message.middleware(user_request_logger)
dp.callback_query.middleware(user_request_logger)
bot.session.middleware(bot_request_logger)
