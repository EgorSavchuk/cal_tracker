"""Export chat_id segments for a reusable broadcast campaign."""

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Sequence

# Campaign settings. Edit these constants per campaign.
START_EVENT = "start"
PAYMENT_EVENTS = {"payment_completed"}
MIN_AGE_DAYS = 3.0
INCLUDE_BLOCKED = False
CONCURRENT_CHECKS = 100
NON_BUYERS_OUTPUT = Path(__file__).with_name("chat_ids_campaign_non_buyers.txt")
PAYERS_OUTPUT = Path(__file__).with_name("chat_ids_campaign_payers.txt")


@dataclass(slots=True)
class UserAnalytics:
    user_id: int
    first_start: datetime | None
    has_payment: bool


def _load_services() -> tuple[
    Callable[[], Any],
    Callable[[int], Awaitable[list[dict[str, Any]]]],
    Callable[[int], Awaitable[bool]],
]:
    bot_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../bot"))
    if bot_dir not in sys.path:
        sys.path.insert(0, bot_dir)

    from services.analytics import get_events, iter_user_ids  # type: ignore
    from services.user_status import is_user_blocked  # type: ignore

    return iter_user_ids, get_events, is_user_blocked


def _chunked(items: Sequence[int], chunk_size: int) -> Iterable[Sequence[int]]:
    for index in range(0, len(items), chunk_size):
        yield items[index : index + chunk_size]


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        return None
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw_value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_event(raw_event: object) -> tuple[str | None, datetime | None]:
    if not isinstance(raw_event, dict):
        return None, None
    event_name = str(raw_event.get("event") or "").strip()
    timestamp = _parse_timestamp(raw_event.get("timestamp"))
    return event_name or None, timestamp


async def _collect_user_analytics(
    *,
    start_event: str,
    payment_events: set[str],
    iter_user_ids_fn: Callable[[], Any],
    get_events_fn: Callable[[int], Awaitable[list[dict[str, Any]]]],
) -> list[UserAnalytics]:
    result: list[UserAnalytics] = []
    async for user_id in iter_user_ids_fn():
        first_start: datetime | None = None
        has_payment = False

        events = await get_events_fn(user_id)
        if not events:
            result.append(UserAnalytics(user_id, first_start, has_payment))
            continue

        for raw_event in events:
            event_name, timestamp = _parse_event(raw_event)
            if not event_name:
                continue

            if event_name == start_event and timestamp is not None:
                if first_start is None or timestamp < first_start:
                    first_start = timestamp
            elif event_name in payment_events:
                has_payment = True

        result.append(UserAnalytics(user_id, first_start, has_payment))
    return result


def _write_chat_ids(path: Path, chat_ids: Sequence[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for chat_id in chat_ids:
            handle.write(f"{chat_id}\n")


async def _exclude_blocked_chat_ids(
    chat_ids: list[int],
    *,
    concurrent_checks: int,
    is_user_blocked_fn: Callable[[int], Awaitable[bool]],
) -> tuple[list[int], list[int]]:
    if not chat_ids:
        return [], []

    allowed: list[int] = []
    blocked: list[int] = []
    safe_concurrency = max(1, concurrent_checks)

    for chunk in _chunked(chat_ids, safe_concurrency):
        statuses = await asyncio.gather(
            *(is_user_blocked_fn(user_id) for user_id in chunk),
            return_exceptions=True,
        )
        for user_id, status in zip(chunk, statuses):
            if isinstance(status, Exception):
                # Fail-open on status check errors: keep user in export.
                allowed.append(user_id)
            elif status:
                blocked.append(user_id)
            else:
                allowed.append(user_id)
    return allowed, blocked


async def async_main() -> int:
    iter_user_ids_fn, get_events_fn, is_user_blocked_fn = _load_services()

    payment_events = {event_name.strip() for event_name in PAYMENT_EVENTS if event_name.strip()}
    if not payment_events:
        raise ValueError("PAYMENT_EVENTS не должен быть пустым.")
    if CONCURRENT_CHECKS < 1:
        raise ValueError("CONCURRENT_CHECKS должен быть >= 1.")

    user_records = await _collect_user_analytics(
        start_event=START_EVENT.strip(),
        payment_events=payment_events,
        iter_user_ids_fn=iter_user_ids_fn,
        get_events_fn=get_events_fn,
    )

    min_age = timedelta(days=MIN_AGE_DAYS)
    now = datetime.now(timezone.utc)

    non_buyers: list[int] = []
    payers: list[int] = []

    for record in user_records:
        if record.has_payment:
            payers.append(record.user_id)
        elif record.first_start is not None and now - record.first_start >= min_age:
            non_buyers.append(record.user_id)

    blocked_non_buyers: list[int] = []
    blocked_payers: list[int] = []
    if not INCLUDE_BLOCKED:
        non_buyers, blocked_non_buyers = await _exclude_blocked_chat_ids(
            non_buyers,
            concurrent_checks=CONCURRENT_CHECKS,
            is_user_blocked_fn=is_user_blocked_fn,
        )
        payers, blocked_payers = await _exclude_blocked_chat_ids(
            payers,
            concurrent_checks=CONCURRENT_CHECKS,
            is_user_blocked_fn=is_user_blocked_fn,
        )

    non_buyers.sort()
    payers.sort()

    _write_chat_ids(NON_BUYERS_OUTPUT, non_buyers)
    _write_chat_ids(PAYERS_OUTPUT, payers)

    print(
        "export complete:\n"
        f"  start_event={START_EVENT!r}\n"
        f"  payment_events={sorted(payment_events)!r}\n"
        f"  min_age_days={MIN_AGE_DAYS}\n"
        f"  include_blocked={INCLUDE_BLOCKED}\n"
        f"  non_buyers({len(non_buyers)}) -> {NON_BUYERS_OUTPUT}\n"
        f"  payers({len(payers)}) -> {PAYERS_OUTPUT}\n"
        f"  blocked_filtered_non_buyers={len(blocked_non_buyers)}\n"
        f"  blocked_filtered_payers={len(blocked_payers)}"
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
