from datetime import datetime, timezone
from typing import Any, AsyncIterator

from loguru import logger
from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection

from config import MONGO_URL, PROJECT_NAME

_client = AsyncMongoClient(MONGO_URL)
_collection = _client["analytics_events"][PROJECT_NAME]


async def log_event(user_id: int, event: str, **data: Any) -> None:
    try:
        await _collection.insert_one(
            {
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc),
                "event": event,
                "data": data,
            }
        )
    except Exception as err:
        logger.exception(
            "analytics: failed to log event user_id={} event={} error={}",
            user_id,
            event,
            err,
        )


async def get_events(
    user_id: int,
    *,
    collection: AsyncCollection | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    coll = collection or _collection
    cursor = coll.find(
        {"user_id": user_id},
        sort=[("timestamp", 1), ("_id", 1)],
        projection={"_id": False},
    )
    async for doc in cursor:
        events.append(
            {
                "timestamp": doc["timestamp"].isoformat(),
                "event": doc.get("event"),
                "data": doc.get("data") or {},
            }
        )
    return events


async def iter_user_ids(
    *,
    collection: AsyncCollection | None = None,
) -> AsyncIterator[int]:
    coll = collection or _collection
    cursor = await coll.aggregate(
        [
            {"$group": {"_id": "$user_id"}},
            {"$sort": {"_id": 1}},
        ],
        allowDiskUse=True,
    )
    async for doc in cursor:
        user_id = doc.get("_id")
        if user_id is None:
            continue
        try:
            yield int(user_id)
        except (TypeError, ValueError):
            continue


async def iter_user_events(
    *,
    collection: AsyncCollection | None = None,
) -> AsyncIterator[tuple[int, list[dict[str, Any]]]]:
    async for user_id in iter_user_ids(collection=collection):
        events = await get_events(user_id, collection=collection)
        if events:
            yield user_id, events
