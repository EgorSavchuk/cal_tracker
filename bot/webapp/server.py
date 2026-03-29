"""aiohttp web application: API endpoints for the WebApp dashboard."""

import hashlib
import hmac
import json
import os
from urllib.parse import parse_qs, unquote

from aiohttp import web

from config import TELEGRAM_BOT_TOKEN, DEBUG
from services import database as db

routes = web.RouteTableDef()


def verify_telegram_webapp(init_data: str) -> int | None:
    """Verify Telegram WebApp initData using HMAC-SHA256.
    Returns user_id if valid, None otherwise.
    """
    try:
        parsed = parse_qs(init_data)
        received_hash = parsed.get("hash", [None])[0]
        if not received_hash:
            return None

        # Build data-check string (sorted key=value, excluding hash)
        data_pairs = []
        for pair in init_data.split("&"):
            key, _, value = pair.partition("=")
            if key != "hash":
                data_pairs.append(f"{key}={unquote(value)}")
        data_pairs.sort()
        data_check_string = "\n".join(data_pairs)

        secret_key = hmac.new(
            b"WebAppData", TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if computed_hash != received_hash:
            return None

        # Extract user_id from initData
        user_data = parsed.get("user", [None])[0]
        if user_data:
            user_obj = json.loads(unquote(user_data))
            return int(user_obj["id"])
        return None
    except Exception:
        return None


@web.middleware
async def auth_middleware(request: web.Request, handler):
    """Check Telegram WebApp auth for /api/ routes, extract user_id."""
    if request.path.startswith("/api/"):
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        user_id = verify_telegram_webapp(init_data) if init_data else None
        if not user_id:
            return web.json_response({"error": "unauthorized"}, status=401)
        request["user_id"] = user_id
    return await handler(request)


@routes.get("/api/profile")
async def api_profile(request: web.Request):
    uid = request["user_id"]
    profile = await db.get_profile(uid)
    weight = float(profile.get("weight", 80))
    height = float(profile.get("height", 172))
    bf = float(profile.get("body_fat", 25))
    plan_kcal = int(profile.get("plan_kcal", 1500))
    target_p = int(profile.get("target_p", 110))
    target_f = int(profile.get("target_f", 55))
    target_c = int(profile.get("target_c", 141))
    tdee_base = int(profile.get("tdee_base", 2000))

    age = int(profile.get("age", 23))
    muscle = float(profile.get("muscle", 0))
    if muscle <= 0:
        muscle = round(weight * (1 - bf / 100) * 0.55, 1)

    return web.json_response({
        "weight": weight,
        "height": height,
        "bf": bf,
        "muscle": muscle,
        "age": age,
        "tdee_base": tdee_base,
        "plan_kcal": plan_kcal,
        "targets": {"kcal": plan_kcal, "p": target_p, "f": target_f, "c": target_c},
    })


@routes.put("/api/profile")
async def api_profile_update(request: web.Request):
    uid = request["user_id"]
    data = await request.json()
    mapping = {
        "weight": "weight",
        "height": "height",
        "bf": "body_fat",
        "age": "age",
        "muscle": "muscle",
        "tdee_base": "tdee_base",
        "plan_kcal": "plan_kcal",
    }
    for key, db_key in mapping.items():
        if key in data:
            await db.set_profile(uid, db_key, str(data[key]))
    targets = data.get("targets")
    if targets:
        if "p" in targets:
            await db.set_profile(uid, "target_p", str(targets["p"]))
        if "f" in targets:
            await db.set_profile(uid, "target_f", str(targets["f"]))
        if "c" in targets:
            await db.set_profile(uid, "target_c", str(targets["c"]))
        if "kcal" in targets:
            await db.set_profile(uid, "plan_kcal", str(targets["kcal"]))
    return web.json_response({"ok": True})


@routes.get("/api/days")
async def api_days(request: web.Request):
    """Return all tracked days with summaries in dashboard format."""
    uid = request["user_id"]
    dates = await db.get_all_dates(uid)
    from_date = request.query.get("from")
    to_date = request.query.get("to")
    if from_date:
        dates = [d for d in dates if d >= from_date]
    if to_date:
        dates = [d for d in dates if d <= to_date]

    days = {}
    for d in dates:
        summary = await db.get_day_summary(uid, d)
        day_num = d.split("-")[2].lstrip("0") or "0"
        days[day_num] = _format_day_for_dashboard(summary)

    return web.json_response({"days": days})


@routes.get("/api/days/{date}")
async def api_day_detail(request: web.Request):
    uid = request["user_id"]
    day_date = request.match_info["date"]
    summary = await db.get_day_summary(uid, day_date)
    return web.json_response(_format_day_for_dashboard(summary))


@routes.get("/api/stats")
async def api_stats(request: web.Request):
    uid = request["user_id"]
    cumulative = await db.get_cumulative_balance(uid)
    return web.json_response(cumulative)


@routes.get("/api/products/top")
async def api_top_products(request: web.Request):
    uid = request["user_id"]
    limit = int(request.query.get("limit", "10"))
    products = await db.get_top_products(uid, limit)
    return web.json_response(products)


@routes.get("/api/recommendations")
async def api_recommendations(request: web.Request):
    """Generate AI-powered nutrition recommendations based on user data."""
    uid = request["user_id"]
    profile = await db.get_profile(uid)
    cumulative = await db.get_cumulative_balance(uid)
    top_products = await db.get_top_products(uid, 10)

    # Get last 7 days stats
    from datetime import date, timedelta
    today = date.today()
    week_ago = today - timedelta(days=7)
    week_stats = await db.get_period_stats(uid, week_ago.isoformat(), today.isoformat())

    plan_kcal = int(profile.get("plan_kcal", 1500))
    target_p = int(profile.get("target_p", 110))
    target_f = int(profile.get("target_f", 55))
    target_c = int(profile.get("target_c", 141))

    # Build context for LLM
    context_parts = [
        f"Профиль: вес {profile.get('weight', 80)}кг, рост {profile.get('height', 172)}см, "
        f"жир {profile.get('body_fat', 25)}%, возраст {profile.get('age', 23)}",
        f"Цель: {plan_kcal} ккал/день, Б{target_p}г Ж{target_f}г У{target_c}г",
    ]

    if week_stats and week_stats.get("days", 0) > 0:
        ws = week_stats
        context_parts.append(
            f"Неделя ({ws['days']}дн): среднее {ws['avg_kcal']}ккал, "
            f"Б{ws['avg_protein']}г Ж{ws['avg_fat']}г У{ws['avg_carbs']}г"
        )

    if cumulative and cumulative.get("days_tracked", 0) > 0:
        cb = cumulative["balance"]
        context_parts.append(
            f"Общий баланс: {'+' if cb >= 0 else ''}{cb}ккал за {cumulative['days_tracked']}дн"
        )

    if top_products:
        items = [f"{p['name']} (×{p['count']})" for p in top_products[:7]]
        context_parts.append(f"Частые блюда: {', '.join(items)}")

    context = "\n".join(context_parts)

    prompt = f"""Проанализируй данные питания пользователя и дай 3-5 коротких персональных рекомендаций.

{context}

Ответь ТОЛЬКО валидным JSON-массивом. Каждый элемент:
{{"type": "warn"|"ok"|"tip", "title": "Заголовок (1-3 слова)", "text": "Рекомендация (1 предложение)"}}

type: "warn" — проблема, "ok" — всё хорошо, "tip" — совет.
Без markdown, без обёрток — только JSON-массив."""

    import aiohttp as aio
    from config import OPENROUTER_API_KEY, OPENROUTER_MODEL

    try:
        async with aio.ClientSession() as session:
            resp = await session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 1000,
                },
                timeout=aio.ClientTimeout(total=15),
            )
            data = await resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            recommendations = json.loads(text)
            return web.json_response(recommendations)
    except Exception as e:
        # Fallback: return empty
        return web.json_response([])


def _format_day_for_dashboard(summary: dict) -> dict:
    """Transform DB summary to dashboard-friendly format."""
    meals = []
    for m in summary["meals"]:
        meals.append({
            "id": m["name"].lower().replace(" ", "_"),
            "name": m["name"],
            "kcal": int(m["kcal"]),
            "p": round(m["protein"]),
            "f": round(m["fat"]),
            "c": round(m["carbs"]),
            "meal": _guess_meal_type(m.get("time", "")),
            "time": m.get("time", ""),
        })

    activities = []
    for a in summary["activities"]:
        activities.append({
            "name": a["name"],
            "duration": a.get("duration", ""),
            "kcal": int(a["kcal"]),
            "category": a.get("category", ""),
        })

    return {
        "meals": meals,
        "activities": activities,
        "totals": {
            "kcal": summary["totals"]["kcal"],
            "p": round(summary["totals"]["protein"]),
            "f": round(summary["totals"]["fat"]),
            "c": round(summary["totals"]["carbs"]),
        },
        "tdee": summary["tdee"],
        "balance": summary["balance"],
        "closed": True,
    }


def _guess_meal_type(time_str: str) -> str:
    """Guess meal type from time."""
    if not time_str:
        return "Другое"
    try:
        hour = int(time_str.split(":")[0])
    except (ValueError, IndexError):
        return "Другое"
    if hour < 11:
        return "Завтрак"
    elif hour < 15:
        return "Обед"
    elif hour < 18:
        return "Перекус"
    else:
        return "Ужин"


@web.middleware
async def cors_middleware(request: web.Request, handler):
    """Allow CORS in DEBUG mode for Vite dev server."""
    if request.method == "OPTIONS":
        resp = web.Response()
    else:
        resp = await handler(request)
    if DEBUG:
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Init-Data"
    return resp


def create_webapp() -> web.Application:
    """Create the aiohttp web application."""
    middlewares = [cors_middleware, auth_middleware]
    app = web.Application(middlewares=middlewares)
    app.add_routes(routes)

    # Serve static files from webapp/dist if it exists
    dist_path = os.path.join(os.path.dirname(__file__), "..", "..", "webapp", "dist")
    dist_path = os.path.normpath(dist_path)
    if os.path.isdir(dist_path):
        app.router.add_static("/", dist_path)

    return app
