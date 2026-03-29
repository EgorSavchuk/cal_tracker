"""Format LLM results and day summaries for Telegram HTML messages."""

from services.llm import AgentResult, MealItem, ActivityItem, ModifyAction


def format_agent_result(result: AgentResult) -> str:
    """Format agent result for display before confirmation."""
    parts = []

    if result.meals:
        parts.append("🍽 <b>Оценка</b>\n")
        lines = []
        for m in result.meals:
            name = m.name
            if m.description:
                name += f" ({m.description})"
            lines.append(
                f"  {name}\n"
                f"  {int(m.kcal)} ккал · Б{int(m.protein)} Ж{int(m.fat)} У{int(m.carbs)}"
            )
        parts.append("\n\n".join(lines))

        if len(result.meals) > 1:
            total_k = sum(m.kcal for m in result.meals)
            total_p = sum(m.protein for m in result.meals)
            total_f = sum(m.fat for m in result.meals)
            total_c = sum(m.carbs for m in result.meals)
            parts.append(
                f"\n\n  <b>Итого: {int(total_k)} ккал · "
                f"Б{int(total_p)} Ж{int(total_f)} У{int(total_c)}</b>"
            )

    if result.activities:
        if result.meals:
            parts.append("\n\n")
        parts.append("🏃 <b>Активность</b>\n")
        for a in result.activities:
            dur = f" · {a.duration}" if a.duration else ""
            cat = f" · {a.category}" if a.category else ""
            parts.append(f"\n  {a.name}{dur}{cat}\n  Расход: {int(a.kcal)} ккал")

    if result.comment:
        parts.append(f"\n\n💬 {result.comment}")

    return "".join(parts)


def format_modification(result: AgentResult) -> str:
    """Format modification preview for confirmation."""
    parts = [f"🔧 <b>Изменение записей</b>\n"]

    if result.mod_description:
        parts.append(f"\n{result.mod_description}\n")

    for mod in (result.modifications or []):
        emoji = {"move": "📦", "edit": "✏️", "delete": "🗑"}.get(mod.action, "🔧")
        table_name = "блюдо" if mod.table == "meals" else "активность"

        if mod.action == "move":
            dest = mod.new_date or ""
            if mod.new_time:
                dest += f" {mod.new_time}"
            parts.append(f"\n{emoji} Перенести {table_name} #{mod.entry_id} → {dest}")
        elif mod.action == "edit":
            changes = []
            if mod.new_values:
                for k, v in mod.new_values.items():
                    changes.append(f"{k}={v}")
            parts.append(f"\n{emoji} Изменить {table_name} #{mod.entry_id}: {', '.join(changes)}")
        elif mod.action == "delete":
            parts.append(f"\n{emoji} Удалить {table_name} #{mod.entry_id}")

    return "".join(parts)


def format_save_products(result: AgentResult) -> str:
    """Format products to be saved."""
    parts = ["⭐ <b>Сохранить продукты</b>\n"]
    for m in (result.meals or []):
        serving = f" ({m.description})" if m.description else ""
        parts.append(
            f"\n  {m.name}{serving}\n"
            f"  {int(m.kcal)} ккал · Б{int(m.protein)} Ж{int(m.fat)} У{int(m.carbs)}"
        )
    return "".join(parts)


def format_day_summary_short(totals: dict, profile: dict[str, str]) -> str:
    """Short summary after recording: eaten / plan + macros."""
    plan_kcal = int(profile.get("plan_kcal", 1500))
    target_p = int(profile.get("target_p", 110))
    target_f = int(profile.get("target_f", 55))
    target_c = int(profile.get("target_c", 141))

    return (
        f"✅ Записано\n\n"
        f"Сегодня: <b>{totals['kcal']} / {plan_kcal}</b> ккал\n"
        f"Б {int(totals['protein'])}/{target_p} · "
        f"Ж {int(totals['fat'])}/{target_f} · "
        f"У {int(totals['carbs'])}/{target_c}"
    )


def format_day_full(summary: dict, profile: dict[str, str]) -> str:
    """Full day view for /day command — like the dashboard."""
    day = summary["date"]
    meals = summary["meals"]
    activities = summary["activities"]
    totals = summary["totals"]
    tdee_base = summary["tdee_base"]
    act_kcal = summary["act_kcal"]
    tdee = summary["tdee"]
    balance = summary["balance"]
    plan_kcal = int(profile.get("plan_kcal", 1500))
    target_p = int(profile.get("target_p", 110))
    target_f = int(profile.get("target_f", 55))
    target_c = int(profile.get("target_c", 141))
    bmr = int(profile.get("bmr", 1666))
    neat = int(tdee_base) - bmr

    parts = [f"📅 <b>{day}</b>"]

    # ── Meals ──
    if meals:
        parts.append("")
        parts.append("🍽 <b>Съедено</b>")
        for m in meals:
            time_str = m.get("time", "")
            time_prefix = f"{time_str} " if time_str else ""
            parts.append(f"  {time_prefix}{m['name']} — {int(m['kcal'])} ккал")
        parts.append(f"\n  <b>Итого: {totals['kcal']} / {plan_kcal} ккал</b>")

    # ── Macros ──
    parts.append("")
    p_ok = "✅" if totals["protein"] >= target_p * 0.9 else "❌"
    f_ok = "✅" if totals["fat"] <= target_f * 1.1 else "❌"
    c_ok = "✅" if totals["carbs"] <= target_c * 1.1 else "❌"
    parts.append(
        f"Б {int(totals['protein'])}/{target_p} {p_ok} · "
        f"Ж {int(totals['fat'])}/{target_f} {f_ok} · "
        f"У {int(totals['carbs'])}/{target_c} {c_ok}"
    )

    # ── Energy expenditure ──
    parts.append("")
    parts.append("🔥 <b>Расход энергии</b>")
    parts.append(f"  Базовый метаболизм (BMR): {bmr}")
    parts.append(f"  Бытовая активность (×1.2): +{neat}")
    if activities:
        for a in activities:
            dur = f" · {a.get('duration', '')}" if a.get("duration") else ""
            cat = f" · {a.get('category', '')}" if a.get("category") else ""
            parts.append(f"  {a['name']}{dur}{cat}: +{int(a['kcal'])}")
    parts.append(f"\n  <b>TDEE: {tdee} ккал</b>")

    # ── Balance ──
    bal_sign = "+" if balance >= 0 else ""
    parts.append("")
    parts.append(f"⚡ Баланс: <b>{bal_sign}{balance} ккал</b>")

    remaining = plan_kcal - totals["kcal"]
    if remaining > 0:
        parts.append(f"🍴 Осталось съесть: {remaining} ккал")

    return "\n".join(parts)


def format_day_close_card(summary: dict, profile: dict[str, str], cumulative_balance: int) -> str:
    """End-of-day card for /close command."""
    day = summary["date"]
    totals = summary["totals"]
    tdee = summary["tdee"]
    tdee_base = summary["tdee_base"]
    act_kcal = summary["act_kcal"]
    balance = summary["balance"]
    target_p = int(profile.get("target_p", 110))
    target_f = int(profile.get("target_f", 55))
    target_c = int(profile.get("target_c", 141))

    p_ok = "✅" if totals["protein"] >= target_p * 0.9 else "❌"
    f_ok = "✅" if totals["fat"] <= target_f * 1.1 else "❌"
    c_ok = "✅" if totals["carbs"] <= target_c * 1.1 else "❌"

    act_str = f"базовый {int(tdee_base)}"
    if act_kcal > 0:
        act_str += f" + активности {int(act_kcal)}"

    bal_sign = "+" if balance >= 0 else ""

    return (
        f"📋 <b>{day}</b>\n\n"
        f"🍽 Съедено: {totals['kcal']} ккал\n"
        f"🔥 TDEE: {tdee} ({act_str})\n"
        f"⚡ Баланс: <b>{bal_sign}{balance}</b>\n\n"
        f"Б {int(totals['protein'])}/{target_p} {p_ok} · "
        f"Ж {int(totals['fat'])}/{target_f} {f_ok} · "
        f"У {int(totals['carbs'])}/{target_c} {c_ok}\n\n"
        f"📈 Накопительный: <b>{'+' if cumulative_balance >= 0 else ''}{cumulative_balance}</b> ккал"
    )
