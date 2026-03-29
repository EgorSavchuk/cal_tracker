"""LLM agent with tool use — routes user messages to appropriate actions."""

import base64
import json
from dataclasses import dataclass, field
from datetime import date, datetime

import aiohttp
from pydantic import BaseModel

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from loader import log

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ── Pydantic models (kept for validation) ────────────────


class MealItem(BaseModel):
    name: str
    description: str = ""
    kcal: float = 0
    protein: float = 0
    fat: float = 0
    carbs: float = 0


class ActivityItem(BaseModel):
    name: str
    duration: str = ""
    kcal: float = 0
    category: str = ""


class ModifyAction(BaseModel):
    action: str  # "move", "edit", "delete"
    table: str  # "meals", "activities"
    entry_id: int
    new_date: str | None = None
    new_time: str | None = None
    new_values: dict | None = None


# ── Agent result ─────────────────────────────────────────


@dataclass
class AgentResult:
    type: str  # "text", "log_food", "log_activity", "modify_entries", "save_products"
    text: str | None = None
    meals: list[MealItem] | None = None
    activities: list[ActivityItem] | None = None
    modifications: list[ModifyAction] | None = None
    mod_description: str | None = None
    comment: str | None = None
    conversation: list[dict] = field(default_factory=list)


# ── Tool definitions ─────────────────────────────────────

ACTION_TOOLS = {"log_food", "log_activity", "modify_entries", "save_products"}
QUERY_TOOLS = {"get_day_data", "get_period_stats", "search_entries", "get_known_products"}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_food",
            "description": (
                "Записать приём пищи. Используй когда пользователь описывает еду которую съел, "
                "присылает фото еды, или упоминает что-то съеденное. "
                "Оцени КБЖУ максимально точно по USDA/Calorizator. "
                "Округляй ккал до 5, БЖУ до 1г. "
                "Если вес не указан — бери стандартную порцию и укажи в description."
            ),
            "parameters": {
                "type": "object",
                "required": ["meals"],
                "properties": {
                    "meals": {
                        "type": "array",
                        "description": "Список блюд/продуктов",
                        "items": {
                            "type": "object",
                            "required": ["name", "kcal", "protein", "fat", "carbs"],
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Устойчивое название БЕЗ граммовки. Одно блюдо = одно name.",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Порция, вес, бренд, способ приготовления",
                                },
                                "kcal": {"type": "number"},
                                "protein": {"type": "number"},
                                "fat": {"type": "number"},
                                "carbs": {"type": "number"},
                            },
                        },
                    },
                    "comment": {
                        "type": "string",
                        "description": "Короткий комментарий к оценке",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_activity",
            "description": (
                "Записать физическую активность. Используй когда пользователь описывает тренировку, "
                "прогулку или другую активность. Расход калорий зависит от веса пользователя."
            ),
            "parameters": {
                "type": "object",
                "required": ["activities"],
                "properties": {
                    "activities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "kcal"],
                            "properties": {
                                "name": {"type": "string"},
                                "duration": {"type": "string", "description": "Длительность, например '30 мин'"},
                                "kcal": {"type": "number", "description": "Расход калорий"},
                                "category": {
                                    "type": "string",
                                    "description": "кардио / силовая / быт",
                                },
                            },
                        },
                    },
                    "comment": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_entries",
            "description": (
                "Изменить существующие записи в базе данных: перенести на другую дату/время, "
                "изменить значения КБЖУ, удалить. Используй когда пользователь просит "
                "исправить, перенести или удалить запись. "
                "ВАЖНО: сначала вызови search_entries или get_day_data чтобы найти ID записей."
            ),
            "parameters": {
                "type": "object",
                "required": ["actions", "description"],
                "properties": {
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["action", "table", "entry_id"],
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["move", "edit", "delete"],
                                },
                                "table": {
                                    "type": "string",
                                    "enum": ["meals", "activities"],
                                },
                                "entry_id": {
                                    "type": "integer",
                                    "description": "ID записи из результатов search_entries/get_day_data",
                                },
                                "new_date": {
                                    "type": "string",
                                    "description": "Новая дата YYYY-MM-DD (для move)",
                                },
                                "new_time": {
                                    "type": "string",
                                    "description": "Новое время HH:MM (для move/edit)",
                                },
                                "new_values": {
                                    "type": "object",
                                    "description": "Новые значения полей (для edit)",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "kcal": {"type": "number"},
                                        "protein": {"type": "number"},
                                        "fat": {"type": "number"},
                                        "carbs": {"type": "number"},
                                    },
                                },
                            },
                        },
                    },
                    "description": {
                        "type": "string",
                        "description": "Человекочитаемое описание изменений для подтверждения пользователем",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_products",
            "description": (
                "Сохранить продукты в базу известных продуктов для точного подсчёта в будущем. "
                "Используй когда пользователь просит запомнить продукт или сохранить его КБЖУ."
            ),
            "parameters": {
                "type": "object",
                "required": ["products"],
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "kcal", "protein", "fat", "carbs"],
                            "properties": {
                                "name": {"type": "string"},
                                "serving": {"type": "string", "description": "Стандартная порция"},
                                "kcal": {"type": "number"},
                                "protein": {"type": "number"},
                                "fat": {"type": "number"},
                                "carbs": {"type": "number"},
                            },
                        },
                    },
                },
            },
        },
    },
    # ── Query tools (auto-executed, results go back to LLM) ──
    {
        "type": "function",
        "function": {
            "name": "get_day_data",
            "description": (
                "Получить подробные данные за конкретный день: все блюда с ID, активности с ID, "
                "итоги КБЖУ, TDEE, баланс. Используй чтобы узнать что пользователь ел/делал "
                "или чтобы найти ID записей перед modify_entries."
            ),
            "parameters": {
                "type": "object",
                "required": ["date"],
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Дата в формате YYYY-MM-DD",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_period_stats",
            "description": "Получить статистику за период: средние значения КБЖУ, баланс, тренды.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_date": {"type": "string", "description": "Начало периода YYYY-MM-DD"},
                    "to_date": {"type": "string", "description": "Конец периода YYYY-MM-DD"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_entries",
            "description": (
                "Поиск записей по имени и/или дате. Возвращает ID, name, date, КБЖУ. "
                "Используй перед modify_entries чтобы найти конкретные записи."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поиск по названию (подстрока)"},
                    "table": {
                        "type": "string",
                        "enum": ["meals", "activities"],
                        "description": "Таблица для поиска (default: meals)",
                    },
                    "date": {"type": "string", "description": "Фильтр по дате YYYY-MM-DD"},
                    "limit": {"type": "integer", "description": "Макс. кол-во результатов (default: 10)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_known_products",
            "description": "Получить список сохранённых известных продуктов пользователя с точными КБЖУ.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ── System prompt builder ────────────────────────────────


def _build_system_prompt(
    profile: dict[str, str],
    known_products: list[dict] | None,
    today_summary: dict | None,
    yesterday_summary: dict | None = None,
    week_stats: dict | None = None,
    cumulative: dict | None = None,
    top_products: list[dict] | None = None,
    is_close: bool = False,
) -> str:
    today_str = date.today().isoformat()
    now_str = datetime.now().strftime("%H:%M")
    plan_kcal = int(profile.get("plan_kcal", 1500))
    target_p = int(profile.get("target_p", 110))
    target_f = int(profile.get("target_f", 55))
    target_c = int(profile.get("target_c", 141))

    # ── Known products ──
    products_section = ""
    if known_products:
        lines = []
        for p in known_products:
            serving = f" ({p['serving']})" if p.get("serving") else ""
            lines.append(
                f"- {p['name']}{serving}: "
                f"{int(p['kcal'])} ккал, Б{int(p['protein'])} Ж{int(p['fat'])} У{int(p['carbs'])}"
            )
        products_section = (
            "\n\n## Известные продукты пользователя\n"
            "Если пользователь упоминает один из этих продуктов — ОБЯЗАТЕЛЬНО используй "
            "ТОЧНЫЕ значения КБЖУ из этого списка. Используй name точно как в списке.\n"
            + "\n".join(lines)
        )

    # ── Today's data ──
    today_section = ""
    if today_summary and (today_summary["meals"] or today_summary["activities"]):
        parts = [f"\n\n## Сегодня ({today_str})"]
        if today_summary["meals"]:
            parts.append("Блюда:")
            for m in today_summary["meals"]:
                t = m.get("time", "")
                parts.append(f"  #{m['id']} {t} {m['name']} — {int(m['kcal'])} ккал Б{int(m['protein'])} Ж{int(m['fat'])} У{int(m['carbs'])}")
        if today_summary["activities"]:
            parts.append("Активности:")
            for a in today_summary["activities"]:
                parts.append(f"  #{a['id']} {a['name']} — {int(a['kcal'])} ккал")
        t = today_summary["totals"]
        parts.append(f"Итого: {t['kcal']}/{plan_kcal} ккал, Б{int(t['protein'])}/{target_p} Ж{int(t['fat'])}/{target_f} У{int(t['carbs'])}/{target_c}")
        parts.append(f"TDEE: {today_summary['tdee']}, Баланс: {today_summary['balance']}")
        remaining = plan_kcal - t["kcal"]
        if remaining > 0:
            parts.append(f"Осталось: {remaining} ккал")
        today_section = "\n".join(parts)
    else:
        today_section = f"\n\n## Сегодня ({today_str})\nПока ничего не записано. План: {plan_kcal} ккал."

    # ── Yesterday's data ──
    yesterday_section = ""
    if yesterday_summary and (yesterday_summary["meals"] or yesterday_summary["activities"]):
        y = yesterday_summary
        yt = y["totals"]
        ybal = y["balance"]
        bal_sign = "+" if ybal >= 0 else ""
        yesterday_section = (
            f"\n\n## Вчера ({y['date']})\n"
            f"Съедено: {yt['kcal']} ккал, Б{int(yt['protein'])} Ж{int(yt['fat'])} У{int(yt['carbs'])}\n"
            f"TDEE: {y['tdee']}, Баланс: {bal_sign}{ybal}"
        )

    # ── Week stats ──
    week_section = ""
    if week_stats and week_stats.get("days", 0) > 0:
        ws = week_stats
        week_section = (
            f"\n\n## Статистика за неделю ({ws.get('from', '?')} — {ws.get('to', '?')}, {ws['days']} дн.)\n"
            f"Среднее: {ws['avg_kcal']} ккал/день, Б{ws['avg_protein']} Ж{ws['avg_fat']} У{ws['avg_carbs']}\n"
            f"Соблюдение плана по ккал: {'да' if abs(ws['avg_kcal'] - plan_kcal) < plan_kcal * 0.15 else 'нет'} (план {plan_kcal})\n"
            f"Соблюдение белка: {'да' if ws['avg_protein'] >= target_p * 0.85 else 'недобор'} (план {target_p}г)"
        )

    # ── Cumulative balance ──
    cumulative_section = ""
    if cumulative and cumulative.get("days_tracked", 0) > 0:
        cb = cumulative["balance"]
        bal_sign = "+" if cb >= 0 else ""
        status = "дефицит" if cb < 0 else "профицит"
        cumulative_section = (
            f"\n\n## Накопительный баланс\n"
            f"{bal_sign}{cb} ккал за {cumulative['days_tracked']} дн. ({status})"
        )

    # ── Top products (eating habits) ──
    habits_section = ""
    if top_products:
        items = [f"  {p['name']} (×{p['count']}, ~{int(p['kcal'])} ккал)" for p in top_products[:7]]
        habits_section = "\n\n## Частые блюда\n" + "\n".join(items)

    # ── Close-day mode ──
    close_section = ""
    if is_close:
        close_section = (
            "\n\n## Режим закрытия дня\n"
            "Пользователь закрывает день. Спроси/обработай информацию об активностях за день. "
            "Используй log_activity для записи активностей."
        )

    return f"""Ты — умный персональный ассистент по питанию и здоровью в Telegram-боте.

## Возможности
1. Записывать еду — оценка КБЖУ через log_food
2. Записывать активности — через log_activity
3. Аналитика — статистика, тренды, советы. Используй get_day_data, get_period_stats, search_entries
4. Править записи — перенос, редактирование, удаление через modify_entries (сначала найди ID)
5. Запоминать продукты — через save_products
6. Отвечать на вопросы о питании — давай персонализированные советы с учётом данных пользователя

## Профиль
- Вес: {profile.get('weight', '80')} кг, Рост: {profile.get('height', '172')} см, Жир: {profile.get('body_fat', '25')}%
- BMR: {profile.get('bmr', '1666')} ккал, TDEE базовый: {profile.get('tdee_base', '2000')} ккал
- Цель: {plan_kcal} ккал/день | Б{target_p}г Ж{target_f}г У{target_c}г

## Правила оценки КБЖУ
- USDA / Calorizator. Округляй ккал до 5, БЖУ до 1г
- Если вес не указан — стандартная порция, укажи в description
- name — устойчивое название БЕЗ граммовки. «Песто 10г» ❌ → name: «Песто», description: «10г» ✅

## Правила работы
- Сегодня: {today_str}, время: {now_str}
- Общайся на русском, кратко и по делу. Обращайся на ты.
- ФОРМАТИРОВАНИЕ: используй HTML-теги для Telegram: <b>жирный</b>, <i>курсив</i>, <code>код</code>. НЕ используй Markdown (**, __, #, ```). Не используй эмодзи чрезмерно.
- Если нужно изменить запись — СНАЧАЛА найди ID через search_entries/get_day_data
- Для персонализированных советов — опирайся на данные ниже (профиль, статистику, привычки)
- Если непонятно что хочет пользователь — спроси

## ВАЖНО: когда вызывать log_food
- Вызывай log_food ТОЛЬКО когда у тебя есть ВСЯ необходимая информация о блюдах
- Если пользователь говорит что пришлёт ещё фото, уточнения или дополнения — НЕ вызывай log_food, ответь текстом и жди
- Если пользователь описал конкретные блюда полностью — тогда вызывай log_food
- Если пользователь прислал фото + голосовое/текст с описанием — объедини всю информацию в один вызов log_food
- Пользователь ведёт свободный диалог. Он может в одном сообщении перечислить еду, а в следующем — уточнить или добавить. Не торопись записывать, пока не будет полная картина
- При modify_entries: меняй ВСЕ указанные поля (название, КБЖУ), а не только название
{products_section}{today_section}{yesterday_section}{week_section}{cumulative_section}{habits_section}{close_section}"""


# ── API call ─────────────────────────────────────────────


async def _call_api(system: str, messages: list[dict], tools: list | None = None) -> dict:
    """Call OpenRouter API."""
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": 0.3,
        "max_tokens": 4000,
    }
    if tools:
        payload["tools"] = tools

    async with aiohttp.ClientSession() as session:
        async with session.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"OpenRouter error {resp.status}: {body}")
            return await resp.json()


# ── Query tool execution ─────────────────────────────────


async def _execute_query(tool_name: str, args: dict, user_id: int) -> dict | list:
    """Execute a query tool and return result data."""
    from services import database as db

    if tool_name == "get_day_data":
        summary = await db.get_day_summary(user_id, args["date"])
        # Include IDs for modifications
        return {
            "date": summary["date"],
            "meals": [
                {
                    "id": m["id"],
                    "name": m["name"],
                    "time": m.get("time", ""),
                    "kcal": int(m["kcal"]),
                    "protein": int(m["protein"]),
                    "fat": int(m["fat"]),
                    "carbs": int(m["carbs"]),
                }
                for m in summary["meals"]
            ],
            "activities": [
                {
                    "id": a["id"],
                    "name": a["name"],
                    "duration": a.get("duration", ""),
                    "kcal": int(a["kcal"]),
                    "category": a.get("category", ""),
                }
                for a in summary["activities"]
            ],
            "totals": summary["totals"],
            "tdee": summary["tdee"],
            "balance": summary["balance"],
        }

    elif tool_name == "get_period_stats":
        return await db.get_period_stats(
            user_id,
            from_date=args.get("from_date"),
            to_date=args.get("to_date"),
        )

    elif tool_name == "search_entries":
        entries = await db.search_entries(
            user_id,
            table=args.get("table", "meals"),
            query=args.get("query"),
            entry_date=args.get("date"),
            limit=args.get("limit", 10),
        )
        return entries

    elif tool_name == "get_known_products":
        products = await db.get_known_products(user_id)
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "serving": p.get("serving", ""),
                "kcal": int(p["kcal"]),
                "protein": int(p["protein"]),
                "fat": int(p["fat"]),
                "carbs": int(p["carbs"]),
            }
            for p in products
        ]

    return {"error": f"Unknown tool: {tool_name}"}


# ── Main agent entry point ───────────────────────────────


def _build_user_content(text: str, images: list[bytes] | None) -> str | list:
    """Build user message content with optional images."""
    if not images:
        return text or ""

    content = []
    for img in images:
        b64 = base64.b64encode(img).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    if text:
        content.append({"type": "text", "text": text})
    return content


async def process_message(
    user_id: int,
    user_text: str,
    profile: dict[str, str],
    images: list[bytes] | None = None,
    known_products: list[dict] | None = None,
    conversation: list[dict] | None = None,
    is_close: bool = False,
) -> AgentResult:
    """Process user message through LLM with tool use. Main entry point."""
    from services import database as db
    from datetime import timedelta

    today = date.today()
    today_str = today.isoformat()
    yesterday_str = (today - timedelta(days=1)).isoformat()
    week_ago_str = (today - timedelta(days=7)).isoformat()

    # Gather enriched context in parallel-ish
    today_summary = await db.get_day_summary(user_id, today_str)
    yesterday_summary = await db.get_day_summary(user_id, yesterday_str)
    week_stats = await db.get_period_stats(user_id, from_date=week_ago_str, to_date=today_str)
    cumulative = await db.get_cumulative_balance(user_id)
    top_products = await db.get_top_products(user_id, limit=7)

    system = _build_system_prompt(
        profile, known_products, today_summary,
        yesterday_summary=yesterday_summary,
        week_stats=week_stats,
        cumulative=cumulative,
        top_products=top_products,
        is_close=is_close,
    )

    if conversation:
        messages = list(conversation)
        # Trim old history to last 20 messages to stay within context limits
        if len(messages) > 20:
            messages = messages[-20:]
        # Add new user message with images if present
        content = _build_user_content(user_text, images)
        if content:
            messages.append({"role": "user", "content": content})
    else:
        messages = []
        content = _build_user_content(user_text, images)
        messages.append({"role": "user", "content": content})

    max_rounds = 5
    for _ in range(max_rounds):
        resp = await _call_api(system, messages, tools=TOOLS)
        assistant_msg = resp["choices"][0]["message"]

        log.info(f"LLM response: tool_calls={bool(assistant_msg.get('tool_calls'))}, content={str(assistant_msg.get('content', ''))[:200]}")

        # Add assistant message to conversation
        messages.append(_clean_message(assistant_msg))

        tool_calls = assistant_msg.get("tool_calls", [])

        if not tool_calls:
            # Pure text response
            return AgentResult(
                type="text",
                text=assistant_msg.get("content", ""),
                conversation=messages,
            )

        # Separate action tools from query tools
        action_calls = [tc for tc in tool_calls if tc["function"]["name"] in ACTION_TOOLS]
        query_calls = [tc for tc in tool_calls if tc["function"]["name"] in QUERY_TOOLS]

        # If there are action tools — return for user confirmation
        if action_calls:
            # Also execute any query tools first
            for tc in query_calls:
                args = json.loads(tc["function"]["arguments"])
                result = await _execute_query(tc["function"]["name"], args, user_id)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

            return _build_action_result(action_calls, assistant_msg, messages)

        # Only query tools — execute and loop back to LLM
        for tc in query_calls:
            args = json.loads(tc["function"]["arguments"])
            result = await _execute_query(tc["function"]["name"], args, user_id)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })

    # Max rounds reached
    return AgentResult(
        type="text",
        text="Не удалось обработать запрос. Попробуй переформулировать.",
        conversation=messages,
    )


def _clean_message(msg: dict) -> dict:
    """Clean assistant message for storage (remove None values)."""
    cleaned = {"role": msg["role"]}
    if msg.get("content"):
        cleaned["content"] = msg["content"]
    if msg.get("tool_calls"):
        cleaned["tool_calls"] = msg["tool_calls"]
    return cleaned


def _build_action_result(
    action_calls: list[dict],
    assistant_msg: dict,
    messages: list[dict],
) -> AgentResult:
    """Build AgentResult from action tool calls."""
    meals = []
    activities = []
    modifications = []
    mod_description = None
    comment = None
    result_type = None

    for tc in action_calls:
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"])

        if name == "log_food":
            result_type = result_type or "log_food"
            for m in args.get("meals", []):
                meals.append(MealItem(**m))
            if args.get("comment"):
                comment = args["comment"]

        elif name == "log_activity":
            result_type = "log_activity" if not meals else "log_food"
            for a in args.get("activities", []):
                activities.append(ActivityItem(**a))
            if args.get("comment"):
                comment = args["comment"]

        elif name == "modify_entries":
            result_type = "modify_entries"
            for action in args.get("actions", []):
                modifications.append(ModifyAction(**action))
            mod_description = args.get("description", "")

        elif name == "save_products":
            result_type = "save_products"
            for p in args.get("products", []):
                meals.append(MealItem(
                    name=p["name"],
                    description=p.get("serving", ""),
                    kcal=p["kcal"],
                    protein=p["protein"],
                    fat=p["fat"],
                    carbs=p["carbs"],
                ))

    # If both meals and activities — combine as log_food
    if meals and activities:
        result_type = "log_food"

    return AgentResult(
        type=result_type or "text",
        text=assistant_msg.get("content"),
        meals=meals or None,
        activities=activities or None,
        modifications=modifications or None,
        mod_description=mod_description,
        comment=comment,
        conversation=messages,
    )
