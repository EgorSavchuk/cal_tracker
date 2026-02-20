"""Send a reusable broadcast campaign by segments, excluding blocked users."""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Sequence

import dotenv
from telegram_sender import TelegramSender, Video

dotenv.load_dotenv()
TOKEN_BOT = os.getenv("TOKEN_BOT")

VARIANT_NON_BUYERS = "non_buyers"
VARIANT_PAYERS = "payers"

# Campaign settings. Edit these constants per campaign.
TARGET_VARIANTS = [VARIANT_PAYERS, VARIANT_NON_BUYERS]
CHAT_ID_FILES = {
    VARIANT_NON_BUYERS: Path(__file__).with_name("chat_ids_campaign_non_buyers.txt"),
    VARIANT_PAYERS: Path(__file__).with_name("chat_ids_campaign_payers.txt"),
}
MESSAGE_TEXT = """<b>Специальное предложение</b>

Мы подготовили короткую акцию для пользователей бота.
Нажмите кнопку ниже, чтобы посмотреть детали предложения."""
BUTTON_TEXT = "Открыть предложение"
CALLBACK_PREFIX = "campaign_offer"
VIDEO_FILE_ID: str | None = None
BATCH_SIZE = 25
CONCURRENT_CHECKS = 100
DRY_RUN = False


def _load_is_user_blocked() -> Callable[[int], Awaitable[bool]]:
    bot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../bot"))
    if bot_dir not in sys.path:
        sys.path.insert(0, bot_dir)

    from services.user_status import is_user_blocked  # type: ignore

    return is_user_blocked


def load_chat_ids(filepath: Path) -> list[int]:
    if not filepath.exists():
        raise FileNotFoundError(f"Файл с chat_id не найден: {filepath}")

    chat_ids: list[int] = []
    with filepath.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                chat_ids.append(int(stripped))
            except ValueError as err:
                raise ValueError(f"Неверное значение chat_id: {stripped!r}") from err

    if not chat_ids:
        raise ValueError(f"Файл {filepath} не содержит ни одного chat_id.")
    return chat_ids


def resolve_log_path(variant: str) -> Path:
    return Path(__file__).with_name(f"send_broadcast_campaign_{variant}.log")


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _chunked(items: Sequence[int], chunk_size: int) -> Sequence[Sequence[int]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _build_reply_markup(variant: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": BUTTON_TEXT,
                    "callback_data": f"{CALLBACK_PREFIX}:{variant}",
                }
            ]
        ]
    }


async def filter_blocked_chat_ids(
    chat_ids: list[int],
    *,
    is_user_blocked_fn: Callable[[int], Awaitable[bool]],
) -> tuple[list[int], list[int]]:
    if not chat_ids:
        return [], []

    allowed: list[int] = []
    blocked: list[int] = []
    safe_concurrency = max(1, CONCURRENT_CHECKS)

    for chunk in _chunked(chat_ids, safe_concurrency):
        statuses = await asyncio.gather(
            *(is_user_blocked_fn(user_id) for user_id in chunk),
            return_exceptions=True,
        )
        for user_id, status in zip(chunk, statuses):
            if isinstance(status, Exception):
                logging.exception(
                    "Не удалось проверить статус block для user_id=%s: %s",
                    user_id,
                    status,
                )
                allowed.append(user_id)
            elif status:
                blocked.append(user_id)
            else:
                allowed.append(user_id)
    return allowed, blocked


async def send_campaign(
    chat_ids: list[int],
    *,
    variant: str,
    token_bot: str,
    log_path: Path,
) -> str:
    if DRY_RUN:
        result_message = f"DRY RUN variant={variant}: total={len(chat_ids)}"
        print(result_message)
        append_log(log_path, result_message)
        return result_message

    media_items = [Video(VIDEO_FILE_ID)] if VIDEO_FILE_ID else []
    sender = TelegramSender(token=token_bot, batch_size=BATCH_SIZE)

    delivered, not_delivered = await sender.run(
        chat_ids,
        text=MESSAGE_TEXT.strip(),
        media_items=media_items,
        reply_markup=_build_reply_markup(variant),
    )
    result_message = (
        f"variant={variant}: total={len(chat_ids)}, delivered={delivered}, failed={not_delivered}"
    )
    print(result_message)
    append_log(log_path, result_message)
    return result_message


async def run_variant(
    variant: str,
    *,
    token_bot: str,
    is_user_blocked_fn: Callable[[int], Awaitable[bool]],
) -> str:
    path = CHAT_ID_FILES.get(variant)
    if not path:
        raise ValueError(f"Неизвестный вариант рассылки: {variant}")

    chat_ids = load_chat_ids(path)
    filtered_chat_ids, blocked_chat_ids = await filter_blocked_chat_ids(
        chat_ids,
        is_user_blocked_fn=is_user_blocked_fn,
    )
    log_path = resolve_log_path(variant)

    filtered_message = (
        f"variant={variant}: total={len(chat_ids)}, blocked={len(blocked_chat_ids)}, "
        f"ready={len(filtered_chat_ids)}"
    )
    print(filtered_message)
    append_log(log_path, filtered_message)

    if not filtered_chat_ids:
        return filtered_message
    return await send_campaign(
        filtered_chat_ids,
        variant=variant,
        token_bot=token_bot,
        log_path=log_path,
    )


async def async_main() -> int:
    if not TOKEN_BOT:
        raise RuntimeError("TOKEN_BOT is not set in environment variables.")
    if BATCH_SIZE < 1:
        raise ValueError("BATCH_SIZE должен быть >= 1.")
    if CONCURRENT_CHECKS < 1:
        raise ValueError("CONCURRENT_CHECKS должен быть >= 1.")
    if not MESSAGE_TEXT.strip():
        raise ValueError("MESSAGE_TEXT не должен быть пустым.")
    if not TARGET_VARIANTS:
        raise ValueError("TARGET_VARIANTS не должен быть пустым.")

    is_user_blocked_fn = _load_is_user_blocked()

    for variant in TARGET_VARIANTS:
        await run_variant(
            variant,
            token_bot=TOKEN_BOT,
            is_user_blocked_fn=is_user_blocked_fn,
        )
    return 0


def main() -> None:
    try:
        exit_code = asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Остановлено пользователем.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"Ошибка: {exc}")
        raise SystemExit(1)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
