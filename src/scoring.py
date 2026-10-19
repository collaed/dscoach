"""R49 - points & persisted daily score. Append-only ledger (score_log),
never an in-place counter, matching the checkin philosophy: every rollup is
a pure aggregation that can be recomputed and audited.

See devdocs/plan-proof-and-scoring.md for the full design.
"""

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from helpers import db


def _coachee_local_date(coachee_id) -> date:
    """Today's date in the coachee's own timezone, not server UTC (REQ-49.4).

    Called by: award_points() below, to stamp every new score_log row.
    """
    c = db()
    c.execute("SELECT timezone FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    tz = ZoneInfo((row and row.get("timezone")) or "UTC")
    return datetime.now(tz).date()


def award_points(coachee_id, points, reason, task_assignment_id=None, note=None):
    """Append one score_log row. Idempotent per (task_assignment_id, reason).

    Called by: routes_coachee.py::complete_task (task_completed, proof_bonus),
    tasks.py::_freeze_overdue (task_missed penalty), routes_coach.py's
    excuse-task handler (miss_reversed). A no-op if points is 0/None, or if a
    row for this exact (task_assignment_id, reason) pair already exists -
    this is what makes re-submitting a form or a double dashboard load safe
    (REQ-49.9). Rows with task_assignment_id=NULL (manual awards) never
    collide with each other - standard SQL unique-constraint NULL semantics.
    """
    if not points:
        return
    c = db()
    if task_assignment_id is not None:
        c.execute(
            "SELECT 1 FROM score_log WHERE task_assignment_id=%s AND reason=%s",
            (task_assignment_id, reason),
        )
        if c.fetchone():
            return
    c.execute(
        "INSERT INTO score_log (coachee_id, points, reason, task_assignment_id, score_date, note) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (coachee_id, points, reason, task_assignment_id, _coachee_local_date(coachee_id).isoformat(), note),
    )


def get_week_start_pref(coach_id, coachee_id=None) -> str:
    """Resolve the Sun-Sat vs Mon-Sun preference (REQ-49.6), coachee override
    beating coach default, both read from the existing `features` JSON column
    (same pattern as photo_validation_pct - no new column needed).

    Called by: scoring summary / rollup screens (coachee dashboard, coach
    view) to decide which week boundary to render.
    """
    c = db()
    c.execute("SELECT features FROM coach WHERE id=%s", (coach_id,))
    row = c.fetchone()
    coach_features = _parse_features(row and row.get("features"))
    pref = coach_features.get("week_start", "mon")
    if coachee_id is not None:
        c.execute("SELECT features FROM coachee WHERE id=%s", (coachee_id,))
        row = c.fetchone()
        coachee_features = _parse_features(row and row.get("features"))
        pref = coachee_features.get("week_start", pref)
    result: str = pref if pref in ("mon", "sun") else "mon"
    return result


def get_proof_bonus(coach_id) -> int:
    """Configurable bonus points for completing a required-proof task with a
    photo attached (REQ-49.10), read from coach.features (same storage
    pattern as week_start) - default 0 (no bonus) if unset.

    Called by: routes_coachee.py::complete_task, right after awarding the
    base task_completed points.
    """
    c = db()
    c.execute("SELECT features FROM coach WHERE id=%s", (coach_id,))
    row = c.fetchone()
    features = _parse_features(row and row.get("features"))
    try:
        return int(features.get("proof_bonus", 0) or 0)
    except (TypeError, ValueError):
        return 0


def get_checkin_bonus(coach_id) -> int:
    """R40: configurable points awarded for a check-in under 'rewarded' checkin_mode,
    read from coach.features (same storage pattern as proof_bonus) - default 0 if unset.

    Called by: routes_coachee.py::submit_checkin.
    """
    c = db()
    c.execute("SELECT features FROM coach WHERE id=%s", (coach_id,))
    row = c.fetchone()
    features = _parse_features(row and row.get("features"))
    try:
        return int(features.get("checkin_bonus", 0) or 0)
    except (TypeError, ValueError):
        return 0


def get_checkin_miss_penalty(coach_id) -> int:
    """R40: configurable points deducted for missing a day's check-in under 'required'
    checkin_mode, read from coach.features - default 0 (no penalty) if unset.

    Called by: tasks.py::_check_required_checkin.
    """
    c = db()
    c.execute("SELECT features FROM coach WHERE id=%s", (coach_id,))
    row = c.fetchone()
    features = _parse_features(row and row.get("features"))
    try:
        return int(features.get("checkin_miss_penalty", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _parse_features(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def daily_totals(coachee_id, since=None) -> dict:
    """Raw per-day point sums for a coachee, optionally from a given date.

    Called by: rollup() below and the score-summary builder - the one query
    every week/month/best-week/all-time figure is derived from in Python, so
    no dialect-specific date/week SQL is ever needed (REQ-49.7).
    """
    c = db()
    if since:
        c.execute(
            "SELECT score_date, SUM(points) AS pts FROM score_log WHERE coachee_id=%s AND score_date >= %s "
            "GROUP BY score_date ORDER BY score_date",
            (coachee_id, since),
        )
    else:
        c.execute(
            "SELECT score_date, SUM(points) AS pts FROM score_log WHERE coachee_id=%s "
            "GROUP BY score_date ORDER BY score_date",
            (coachee_id,),
        )
    totals = {}
    for row in c.fetchall():
        d = row["score_date"]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        totals[d] = row["pts"] or 0
    return totals


def week_key(d: date, week_start: str) -> date:
    """The Monday (week_start='mon') or Sunday (week_start='sun') that starts d's week."""
    offset = d.weekday() if week_start == "mon" else (d.weekday() + 1) % 7
    return d - timedelta(days=offset)


def rollup(daily: dict, mode: str, week_start: str = "mon") -> dict:
    """Bucket a daily_totals() dict into week/month sums. Pure, no DB access."""
    buckets: dict = {}
    for d, pts in daily.items():
        if mode == "week":
            key = week_key(d, week_start)
        elif mode == "month":
            key = d.replace(day=1)
        else:
            key = d
        buckets[key] = buckets.get(key, 0) + pts
    return buckets


def score_summary(coachee_id, coach_id, week_start=None) -> dict:
    """Today / this-week / this-month / all-time / best-week totals for the
    score widget.

    Called by: routes_coachee.py::coachee_dashboard() and
    routes_coach.py::coach_view_coachee() - same computation, both screens
    (REQ-49.8).
    """
    ws = week_start or get_week_start_pref(coach_id, coachee_id)
    today = _coachee_local_date(coachee_id)
    daily = daily_totals(coachee_id)
    weeks = rollup(daily, "week", ws)
    months = rollup(daily, "month", ws)
    this_week_key = week_key(today, ws)
    this_month_key = today.replace(day=1)
    return {
        "today": daily.get(today, 0),
        "this_week": weeks.get(this_week_key, 0),
        "this_month": months.get(this_month_key, 0),
        "all_time": sum(daily.values()),
        "best_week": max(weeks.values()) if weeks else 0,
        "week_start": ws,
    }


def score_history(coachee_id, limit=30) -> list:
    """Most recent line-item score_log entries for a coachee (coach's audit view).

    Called by: routes_coach.py::coach_view_coachee() - the "Score" section's
    line-item history (REQ-49.8, DES-49.3's "coach sees exactly how each
    point was earned or lost").
    """
    c = db()
    c.execute(
        "SELECT * FROM score_log WHERE coachee_id=%s ORDER BY created_at DESC LIMIT %s",
        (coachee_id, limit),
    )
    rows: list = c.fetchall()
    return rows
