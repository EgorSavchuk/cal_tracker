from datetime import UTC, datetime

from loguru import logger
from pymongo import AsyncMongoClient

from config import MONGO_URL, PROJECT_NAME

_client = AsyncMongoClient(MONGO_URL)
_collection = _client["user_status"][PROJECT_NAME]


async def is_user_blocked(user_id: int) -> bool:
    try:
        doc = await _collection.find_one(
            {"user_id": user_id},
            projection={"_id": False, "is_blocked": True},
        )
    except Exception as err:
        logger.exception(
            "user_status: failed to read status user_id={} error={}",
            user_id,
            err,
        )
        return False
    return bool(doc and doc.get("is_blocked"))


async def mark_user_blocked(user_id: int) -> None:
    now = datetime.now(UTC)
    try:
        await _collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "is_blocked": True,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )
    except Exception as err:
        logger.exception(
            "user_status: failed to mark blocked user_id={} error={}",
            user_id,
            err,
        )


async def clear_user_blocked(user_id: int) -> None:
    now = datetime.now(UTC)
    try:
        await _collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "is_blocked": False,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )
    except Exception as err:
        logger.exception(
            "user_status: failed to clear blocked user_id={} error={}",
            user_id,
            err,
        )
