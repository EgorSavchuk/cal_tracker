from typing import Any
from typing import Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.middlewares.base import (
    NextRequestMiddlewareType,
    BaseRequestMiddleware,
)
from aiogram.methods import TelegramMethod, GetMe
from aiogram.methods.base import Response, TelegramType
from aiogram.types import TelegramObject
from pymongo import AsyncMongoClient

from config import MONGO_URL, PROJECT_NAME

_client = AsyncMongoClient(MONGO_URL)
_collection = _client["all_message_logging_bot"][PROJECT_NAME]


class UserRequestLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        log_dict = event.model_dump(exclude_defaults=True, exclude_none=True)
        await _collection.insert_one(log_dict)
        return await handler(event, data)


class BotRequestLoggingMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        result = await make_request(bot, method)
        if hasattr(result, "model_dump") and type(method) is not GetMe:
            log_dict = result.model_dump(exclude_defaults=True, exclude_none=True)
            await _collection.insert_one(log_dict)
        return result
