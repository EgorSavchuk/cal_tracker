from datetime import UTC, datetime, timedelta

from loguru import logger

from config import ADMIN_IDS
from loader import bot
from taskiq_worker import broker, redis_source


async def _notify_admins(text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode=None)
        except Exception as exc:
            logger.exception(
                "Failed to notify admin {} in background task: {}",
                admin_id,
                exc,
            )


@broker.task
async def send_text_message_task(chat_id: int, text: str) -> None:
    """Universal background sender for plain text messages."""
    try:
        await bot.send_message(chat_id, text)
    except Exception as exc:
        logger.exception("send_text_message_task failed for {}: {}", chat_id, exc)


@broker.task
async def notify_admins_task(text: str) -> None:
    """Background notification for all admins from ADMIN_IDS."""
    await _notify_admins(text)


@broker.task(schedule=[{"cron": "0 * * * *", "cron_offset": "UTC"}])
async def heartbeat_task() -> None:
    """Example cron task for scheduler health checks."""
    logger.info("taskiq heartbeat: scheduler is alive")


async def schedule_text_message(
    chat_id: int,
    text: str,
    *,
    delay: timedelta,
) -> None:
    """Helper to schedule deferred messages from handlers/services."""
    eta = datetime.now(UTC) + delay
    await send_text_message_task.schedule_by_time(
        redis_source,
        eta,
        chat_id=chat_id,
        text=text,
    )
