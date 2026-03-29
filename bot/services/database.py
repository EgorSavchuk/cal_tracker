import os
from datetime import date, datetime

import aiosqlite

from config import DB_PATH

_db: aiosqlite.Connection | None = None

PROFILE_DEFAULTS = {
    "weight": "80",
    "height": "172",
    "body_fat": "25",
    "bmr": "1666",
    "tdee_base": "2000",
    "plan_kcal": "1500",
    "target_p": "110",
    "target_f": "55",
    "target_c": "141",
}


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _create_tables(_db)
    return _db


async def _create_tables(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT,
            name TEXT NOT NULL,
            description TEXT,
            kcal REAL DEFAULT 0,
            protein REAL DEFAULT 0,
            fat REAL DEFAULT 0,
            carbs REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            name TEXT NOT NULL,
            duration TEXT,
            kcal REAL DEFAULT 0,
            category TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS profile (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );

        CREATE TABLE IF NOT EXISTS known_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            serving TEXT,
            kcal REAL NOT NULL,
            protein REAL NOT NULL,
            fat REAL NOT NULL,
            carbs REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, name)
        );
    """)
    await _migrate(db)
    await db.commit()


async def _migrate(db: aiosqlite.Connection) -> None:
    """Add user_id columns to existing tables if missing (migration from single-user)."""
    for table in ("meals", "activities"):
        cols = await db.execute_fetchall(f"PRAGMA table_info({table})")
        col_names = [c["name"] for c in cols]
        if "user_id" not in col_names:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")

    # Migrate profile: old schema was (key TEXT PK, value TEXT)
    cols = await db.execute_fetchall("PRAGMA table_info(profile)")
    col_names = [c["name"] for c in cols]
    if "user_id" not in col_names:
        # Old single-user profile → migrate
        await db.execute("ALTER TABLE profile RENAME TO profile_old")
        await db.execute("""
            CREATE TABLE profile (
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
        """)
        await db.execute("INSERT INTO profile (user_id, key, value) SELECT 0, key, value FROM profile_old")
        await db.execute("DROP TABLE profile_old")

    # Migrate known_products
    cols = await db.execute_fetchall("PRAGMA table_info(known_products)")
    col_names = [c["name"] for c in cols]
    if "user_id" not in col_names:
        await db.execute("ALTER TABLE known_products ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


# ── Users ───────────────────────────────────────────────


async def get_user(user_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    )
    return dict(rows[0]) if rows else None


async def create_user(user_id: int, username: str | None, full_name: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
        (user_id, username, full_name),
    )
    await db.commit()


async def set_user_status(user_id: int, status: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE users SET status = ? WHERE user_id = ?", (status, user_id)
    )
    await db.commit()


async def get_approved_users() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM users WHERE status = 'approved'")
    return [dict(r) for r in rows]


# ── Profile ──────────────────────────────────────────────


async def get_profile(user_id: int) -> dict[str, str]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT key, value FROM profile WHERE user_id = ?", (user_id,)
    )
    profile = {r["key"]: r["value"] for r in rows}
    # Fill defaults for missing keys
    for key, value in PROFILE_DEFAULTS.items():
        if key not in profile:
            profile[key] = value
    return profile


async def set_profile(user_id: int, key: str, value: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO profile (user_id, key, value) VALUES (?, ?, ?)",
        (user_id, key, value),
    )
    await db.commit()


# ── Meals ────────────────────────────────────────────────


async def add_meal(
    user_id: int,
    meal_date: str,
    meal_time: str,
    name: str,
    description: str | None,
    kcal: float,
    protein: float,
    fat: float,
    carbs: float,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO meals (user_id, date, time, name, description, kcal, protein, fat, carbs)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, meal_date, meal_time, name, description, kcal, protein, fat, carbs),
    )
    await db.commit()
    return cursor.lastrowid


async def get_meals_by_date(user_id: int, day: str) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM meals WHERE user_id = ? AND date = ? ORDER BY time, id",
        (user_id, day),
    )
    return [dict(r) for r in rows]


# ── Activities ───────────────────────────────────────────


async def add_activity(
    user_id: int,
    act_date: str,
    name: str,
    duration: str | None,
    kcal: float,
    category: str,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO activities (user_id, date, name, duration, kcal, category)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, act_date, name, duration, kcal, category),
    )
    await db.commit()
    return cursor.lastrowid


async def get_activities_by_date(user_id: int, day: str) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM activities WHERE user_id = ? AND date = ? ORDER BY id",
        (user_id, day),
    )
    return [dict(r) for r in rows]


# ── Day summary ──────────────────────────────────────────


async def get_day_summary(user_id: int, day: str) -> dict:
    meals = await get_meals_by_date(user_id, day)
    activities = await get_activities_by_date(user_id, day)
    profile = await get_profile(user_id)

    total_kcal = sum(m["kcal"] for m in meals)
    total_p = sum(m["protein"] for m in meals)
    total_f = sum(m["fat"] for m in meals)
    total_c = sum(m["carbs"] for m in meals)
    act_kcal = sum(a["kcal"] for a in activities)
    tdee_base = float(profile.get("tdee_base", 2000))
    tdee = tdee_base + act_kcal
    balance = total_kcal - tdee

    return {
        "date": day,
        "meals": meals,
        "activities": activities,
        "totals": {
            "kcal": round(total_kcal),
            "protein": round(total_p, 1),
            "fat": round(total_f, 1),
            "carbs": round(total_c, 1),
        },
        "tdee_base": tdee_base,
        "act_kcal": act_kcal,
        "tdee": round(tdee),
        "balance": round(total_kcal - tdee),
    }


# ── Undo ─────────────────────────────────────────────────


async def delete_last_entry(user_id: int) -> str | None:
    """Delete the most recently created meal or activity. Returns description."""
    db = await get_db()
    meal = await db.execute_fetchall(
        "SELECT id, name, created_at FROM meals WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    act = await db.execute_fetchall(
        "SELECT id, name, created_at FROM activities WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,),
    )

    meal_row = dict(meal[0]) if meal else None
    act_row = dict(act[0]) if act else None

    if not meal_row and not act_row:
        return None

    if meal_row and act_row:
        if meal_row["created_at"] >= act_row["created_at"]:
            target = ("meals", meal_row)
        else:
            target = ("activities", act_row)
    elif meal_row:
        target = ("meals", meal_row)
    else:
        target = ("activities", act_row)

    table, row = target
    await db.execute(f"DELETE FROM {table} WHERE id = ?", (row["id"],))
    await db.commit()
    label = "🍽" if table == "meals" else "🏃"
    return f"{label} {row['name']}"


# ── Stats / WebApp ───────────────────────────────────────


async def get_all_dates(user_id: int) -> list[str]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT DISTINCT date FROM (
            SELECT date FROM meals WHERE user_id = ?
            UNION
            SELECT date FROM activities WHERE user_id = ?
        ) ORDER BY date""",
        (user_id, user_id),
    )
    return [r["date"] for r in rows]


async def get_cumulative_balance(user_id: int) -> dict:
    dates = await get_all_dates(user_id)
    total_balance = 0
    for d in dates:
        summary = await get_day_summary(user_id, d)
        total_balance += summary["balance"]
    return {
        "balance": round(total_balance),
        "days_tracked": len(dates),
        "start_date": dates[0] if dates else "",
    }


async def get_top_products(user_id: int, limit: int = 10) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        """SELECT name, COUNT(*) as count,
                  ROUND(AVG(kcal)) as kcal,
                  ROUND(AVG(protein), 1) as protein,
                  ROUND(AVG(fat), 1) as fat,
                  ROUND(AVG(carbs), 1) as carbs
           FROM meals WHERE user_id = ? GROUP BY name ORDER BY count DESC LIMIT ?""",
        (user_id, limit),
    )
    return [dict(r) for r in rows]


# ── Known Products ──────────────────────────────────────


async def add_known_product(
    user_id: int,
    name: str,
    serving: str | None,
    kcal: float,
    protein: float,
    fat: float,
    carbs: float,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        """INSERT OR REPLACE INTO known_products (user_id, name, serving, kcal, protein, fat, carbs)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, name, serving, kcal, protein, fat, carbs),
    )
    await db.commit()
    return cursor.lastrowid


async def get_known_products(user_id: int) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM known_products WHERE user_id = ? ORDER BY name",
        (user_id,),
    )
    return [dict(r) for r in rows]


async def delete_known_product(user_id: int, product_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM known_products WHERE id = ? AND user_id = ?",
        (product_id, user_id),
    )
    await db.commit()
    return cursor.rowcount > 0


# ── Search & Modify ─────────────────────────────────────


async def search_entries(
    user_id: int,
    table: str = "meals",
    query: str | None = None,
    entry_date: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search meals or activities by name and/or date."""
    db = await get_db()
    if table not in ("meals", "activities"):
        return []

    conditions = ["user_id = ?"]
    params: list = [user_id]

    if entry_date:
        conditions.append("date = ?")
        params.append(entry_date)
    if query:
        conditions.append("name LIKE ?")
        params.append(f"%{query}%")

    where = " AND ".join(conditions)
    params.append(limit)
    rows = await db.execute_fetchall(
        f"SELECT * FROM {table} WHERE {where} ORDER BY date DESC, id DESC LIMIT ?",
        tuple(params),
    )
    return [dict(r) for r in rows]


async def get_entry_by_id(user_id: int, table: str, entry_id: int) -> dict | None:
    """Get a single entry by ID."""
    db = await get_db()
    if table not in ("meals", "activities"):
        return None
    rows = await db.execute_fetchall(
        f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    return dict(rows[0]) if rows else None


async def update_meal(user_id: int, entry_id: int, **updates) -> bool:
    """Update meal fields. Allowed: date, time, name, description, kcal, protein, fat, carbs."""
    db = await get_db()
    allowed = {"date", "time", "name", "description", "kcal", "protein", "fat", "carbs"}
    fields = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not fields:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [entry_id, user_id]
    cursor = await db.execute(
        f"UPDATE meals SET {set_clause} WHERE id = ? AND user_id = ?",
        tuple(values),
    )
    await db.commit()
    return cursor.rowcount > 0


async def update_activity(user_id: int, entry_id: int, **updates) -> bool:
    """Update activity fields. Allowed: date, name, duration, kcal, category."""
    db = await get_db()
    allowed = {"date", "name", "duration", "kcal", "category"}
    fields = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not fields:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [entry_id, user_id]
    cursor = await db.execute(
        f"UPDATE activities SET {set_clause} WHERE id = ? AND user_id = ?",
        tuple(values),
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_entry(user_id: int, table: str, entry_id: int) -> str | None:
    """Delete a specific entry by ID. Returns name if deleted."""
    db = await get_db()
    if table not in ("meals", "activities"):
        return None
    rows = await db.execute_fetchall(
        f"SELECT name FROM {table} WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    if not rows:
        return None
    name = rows[0]["name"]
    await db.execute(f"DELETE FROM {table} WHERE id = ? AND user_id = ?", (entry_id, user_id))
    await db.commit()
    return name


async def get_period_stats(user_id: int, from_date: str | None = None, to_date: str | None = None) -> dict:
    """Get aggregated stats for a date range."""
    dates = await get_all_dates(user_id)
    if from_date:
        dates = [d for d in dates if d >= from_date]
    if to_date:
        dates = [d for d in dates if d <= to_date]

    if not dates:
        return {"days": 0, "summaries": []}

    summaries = []
    total_kcal = 0
    total_p = 0
    total_f = 0
    total_c = 0
    total_balance = 0

    for d in dates:
        s = await get_day_summary(user_id, d)
        summaries.append({
            "date": d,
            "kcal": s["totals"]["kcal"],
            "protein": round(s["totals"]["protein"]),
            "fat": round(s["totals"]["fat"]),
            "carbs": round(s["totals"]["carbs"]),
            "tdee": s["tdee"],
            "balance": s["balance"],
        })
        total_kcal += s["totals"]["kcal"]
        total_p += s["totals"]["protein"]
        total_f += s["totals"]["fat"]
        total_c += s["totals"]["carbs"]
        total_balance += s["balance"]

    n = len(dates)
    return {
        "days": n,
        "from": dates[0],
        "to": dates[-1],
        "avg_kcal": round(total_kcal / n),
        "avg_protein": round(total_p / n),
        "avg_fat": round(total_f / n),
        "avg_carbs": round(total_c / n),
        "total_balance": round(total_balance),
        "summaries": summaries,
    }
