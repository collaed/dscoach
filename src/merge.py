"""Mail-Merge Variable Substitution Engine."""

from datetime import date, datetime

from helpers import db, utcnow

_merge_cache = {}  # coachee_id -> (timestamp, vars_dict) — cache per request cycle


def _get_merge_context(coachee_id):
    """PURPOSE: Build the mail-merge variable dict for a coachee (name, streak, level, grade_avg,
    days_active, strikes, date, avatar, safe_word, etc.), cached per coachee within a request.
    CALLED BY / SCREEN: _merge_vars() here and automation.py — feeds coachee dashboard/tasks/notes/
    conditioning/rituals text (/me screens) and coach automation actions.
    WHEN: on first merge for a coachee during a request (e.g. coachee dashboard load, task render)."""
    now_ts = int(utcnow().timestamp())
    cached = _merge_cache.get(coachee_id)
    if cached and cached[0] == now_ts:
        return cached[1]

    c = db()
    c.execute("SELECT * FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    if not row:
        return {}

    # Compute grade average
    c.execute(
        "SELECT grade FROM task_assignment WHERE coachee_id=%s AND grade IS NOT NULL ORDER BY responded_at DESC LIMIT 20",
        (coachee_id,),
    )
    grades = [r["grade"] for r in c.fetchall()]
    grade_map = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
    avg_num = sum(grade_map.get(g, 4) for g in grades) / len(grades) if grades else 0
    grade_avg = next((k for k, v in grade_map.items() if v >= round(avg_num)), "\u2014") if grades else "\u2014"

    # Compute days active
    created = row.get("created_at")
    if created:
        if isinstance(created, str):
            try:
                created_date = datetime.fromisoformat(created.split(" ")[0]).date()
            except ValueError:
                created_date = date.today()
        elif hasattr(created, "date"):
            created_date = created.date()
        else:
            created_date = date.today()
        days_active = (date.today() - created_date).days
    else:
        days_active = 0

    # Level
    best_streak = max(row.get("current_streak") or 0, row.get("best_streak") or 0)
    levels = [
        ("Initiate", 0), ("Dedicated", 7), ("Disciplined", 14),
        ("Devoted", 30), ("Exemplary", 60), ("Transcendent", 90),
    ]
    level_name = "Initiate"
    for name, threshold in levels:
        if best_streak >= threshold:
            level_name = name

    today = date.today()
    ctx = {
        "name": row.get("name", ""),
        "streak": str(row.get("current_streak") or 0),
        "best_streak": str(best_streak),
        "level": level_name,
        "grade_avg": grade_avg,
        "days_active": str(days_active),
        "strikes": str(row.get("strikes") or 0),
        "date": today.isoformat(),
        "day_of_week": today.strftime("%A"),
        "avatar": row.get("avatar") or "\U0001f415",
        "safe_word": row.get("safe_word") or "RED",
    }
    _merge_cache[coachee_id] = (now_ts, ctx)
    return ctx


def _merge_vars(text, coachee_id):
    """PURPOSE: Replace {{variable}} placeholders in text with the coachee's merge-context values.
    CALLED BY / SCREEN: routes_coachee.py (conditioning, notes, rituals on /me dashboard),
    tasks.py (task title/desc, onboarding notes), automation.py (auto-note/rule action text).
    WHEN: on render of coachee-facing text (dashboard/tasks load) and when automations fire."""
    if not text or "{{" not in text:
        return text
    ctx = _get_merge_context(coachee_id)
    for key, val in ctx.items():
        text = text.replace("{{" + key + "}}", val)
    return text
