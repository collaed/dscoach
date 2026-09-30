"""Task management helpers: auto-assign, freeze, streak, visibility, features."""

import json
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from helpers import _rand_func, db
from merge import _merge_vars

FEATURES = [
    ("tasks", "\U0001f4cb Tasks & Grading"),
    ("checkins", "\U0001f4d6 Check-ins"),
    ("tracking", "\U0001f4ca Tracking"),
    ("conditioning", "\U0001f9e0 Mental Conditioning"),
    ("notes", "\U0001f4ac Notes & Voice"),
    ("goals", "\U0001f3af Goal Setting"),
    ("journal", "\U0001f4d3 Journaling"),
    ("writing", "\u270d\ufe0f Creative Writing"),
    ("photos", "\U0001f4f8 Progress Photos"),
    ("ai_profile", "\U0001fa9e AI Profile"),
    ("telegram", "\U0001f4f1 Telegram Notifications"),
    ("payments", "\U0001f4b3 Payment Tracking"),
]


def _features_for(coach_id, coachee_id=None):
    """Get effective feature flags. Coach global, optionally overridden per coachee."""
    c = db()
    c.execute("SELECT features FROM coach WHERE id=%s", (coach_id,))
    row = c.fetchone()
    raw = row["features"] if row else None
    if raw and isinstance(raw, str):
        coach_f = json.loads(raw)
    elif raw and isinstance(raw, dict):
        coach_f = raw
    else:
        coach_f = {k: True for k, _ in FEATURES}
    if not coachee_id:
        return coach_f
    c.execute("SELECT features FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    raw2 = row["features"] if row else None
    if raw2 and isinstance(raw2, str):
        coachee_f = json.loads(raw2)
    elif raw2 and isinstance(raw2, dict):
        coachee_f = raw2
    else:
        coachee_f = {}
    # coachee can only disable what coach enabled
    return {k: coach_f.get(k, True) and coachee_f.get(k, True) for k, _ in FEATURES}


def _auto_assign_reserves(coachee_id, coach_id):
    """If no task was manually assigned today for this coachee, pick one reserve task."""
    c = db()
    c.execute("SELECT timezone, task_unveil_time, task_freeze_time FROM coachee WHERE id=%s", (coachee_id,))
    cc = c.fetchone()
    tz = ZoneInfo((cc["timezone"]) or "UTC")
    local_today = datetime.now(tz).date().isoformat()

    def _assign(tmpl_id, due):
        vis = f"{due} {cc['task_unveil_time']}" if cc["task_unveil_time"] else None
        frz = f"{due} {cc['task_freeze_time']}" if cc["task_freeze_time"] else None
        c.execute(
            "INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after) VALUES (%s,%s,%s,%s,%s)",
            (tmpl_id, coachee_id, due, vis, frz),
        )

    # recurring tasks: auto-assign if due
    c.execute(
        """SELECT tt.id, tt.recur_days, tt.recur_approx FROM task_template tt
                 WHERE tt.coach_id=%s AND tt.recur_days IS NOT NULL AND tt.recur_days > 0 AND tt.is_reserve=0""",
        (coach_id,),
    )
    for tmpl in c.fetchall():
        c.execute(
            "SELECT MAX(due_date) as last_due FROM task_assignment WHERE template_id=%s AND coachee_id=%s",
            (tmpl["id"], coachee_id),
        )
        last = c.fetchone()["last_due"]
        if last:
            days = tmpl["recur_days"]
            if tmpl["recur_approx"]:
                days = max(1, days + random.randint(-max(1, days // 4), max(1, days // 4)))
            next_due = (last + timedelta(days=days)).isoformat()
            if next_due <= local_today:
                _assign(tmpl["id"], local_today)
        # if never assigned to this coachee, assign now
        else:
            _assign(tmpl["id"], local_today)

    # reserve tasks: only if no task today at all
    c.execute(
        "SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND due_date=%s", (coachee_id, local_today)
    )
    if c.fetchone()["cnt"] > 0:
        return

    # Week planner: check if there's a plan entry for today's day of week
    day_of_week = datetime.now(tz).weekday()  # 0=Monday
    c.execute(
        "SELECT template_id FROM week_plan WHERE coach_id=%s AND day_of_week=%s AND (coachee_id=%s OR coachee_id IS NULL)",
        (coach_id, day_of_week, coachee_id),
    )
    plan_entries = c.fetchall()
    for entry in plan_entries:
        c.execute(
            "SELECT id FROM task_assignment WHERE template_id=%s AND coachee_id=%s AND due_date=%s",
            (entry["template_id"], coachee_id, local_today),
        )
        if not c.fetchone():
            _assign(entry["template_id"], local_today)

    # Re-check if any tasks now exist for today (from week plan)
    c.execute(
        "SELECT COUNT(*) as cnt FROM task_assignment WHERE coachee_id=%s AND due_date=%s", (coachee_id, local_today)
    )
    if c.fetchone()["cnt"] > 0:
        return

    # Fall back to reserve tasks
    c.execute(
        f"""SELECT tt.id FROM task_template tt
                 WHERE tt.coach_id=%s AND tt.is_reserve=1
                 AND tt.id NOT IN (SELECT template_id FROM task_assignment WHERE coachee_id=%s)
                 ORDER BY {_rand_func()} LIMIT 1""",  # nosec B608 - _rand_func() returns fixed SQL keyword
        (coach_id, coachee_id),
    )
    row = c.fetchone()
    if row:
        _assign(row["id"], local_today)


def _freeze_overdue(coachee_id, tz):
    """Mark pending tasks as missed if past freeze time, add strikes, reset streak."""
    from automation import _auto_escalation_note, _run_auto_rules

    c = db()
    local_now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        """SELECT COUNT(*) as cnt FROM task_assignment
                 WHERE coachee_id=%s AND status='pending' AND frozen_after IS NOT NULL AND frozen_after < %s""",
        (coachee_id, local_now),
    )
    missed = c.fetchone()["cnt"]
    if missed:
        c.execute(
            """UPDATE task_assignment SET status='missed'
                     WHERE coachee_id=%s AND status='pending' AND frozen_after IS NOT NULL AND frozen_after < %s""",
            (coachee_id, local_now),
        )
        c.execute("UPDATE coachee SET strikes=strikes+%s, current_streak=0 WHERE id=%s", (missed, coachee_id))
        # Auto-escalation note
        _auto_escalation_note(coachee_id, missed)
        # Run automation rules for task_missed trigger
        _run_auto_rules(coachee_id, "task_missed")


def _update_streak(coachee_id, tz):
    """Update streak if all tasks for yesterday were completed on time."""
    from automation import _run_auto_rules, _streak_milestone_note

    c = db()
    local_today = datetime.now(tz).date()
    yesterday = (local_today - timedelta(days=1)).isoformat()
    c.execute("SELECT last_streak_date FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    if row["last_streak_date"] and str(row["last_streak_date"]) >= yesterday:
        return  # already checked
    c.execute(
        "SELECT COUNT(*) as total FROM task_assignment WHERE coachee_id=%s AND due_date=%s", (coachee_id, yesterday)
    )
    total = c.fetchone()["total"]
    if total == 0:
        return  # no tasks yesterday
    c.execute(
        "SELECT COUNT(*) as done FROM task_assignment WHERE coachee_id=%s AND due_date=%s AND status='completed'",
        (coachee_id, yesterday),
    )
    if c.fetchone()["done"] == total:
        c.execute(
            """UPDATE coachee SET current_streak=current_streak+1,
                     best_streak=CASE WHEN best_streak > current_streak+1 THEN best_streak ELSE current_streak+1 END,
                     last_streak_date=%s WHERE id=%s""",
            (yesterday, coachee_id),
        )
        # Check for streak milestones
        c.execute("SELECT current_streak FROM coachee WHERE id=%s", (coachee_id,))
        new_streak = c.fetchone()["current_streak"]
        _streak_milestone_note(coachee_id, new_streak)
        _run_auto_rules(coachee_id, "streak_milestone")
    else:
        c.execute("UPDATE coachee SET current_streak=0, last_streak_date=%s WHERE id=%s", (yesterday, coachee_id))


def _visible_tasks(coachee_id, tz):
    """Get tasks that are visible, not frozen, and whose dependencies are met."""
    c = db()
    local_now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        """SELECT ta.*, tt.title, tt.description as task_desc, tt.category, tt.difficulty
                 FROM task_assignment ta JOIN task_template tt ON ta.template_id=tt.id
                 WHERE ta.coachee_id=%s AND ta.status IN ('pending','partial')
                 AND (ta.visible_after IS NULL OR ta.visible_after <= %s)
                 AND (ta.frozen_after IS NULL OR ta.frozen_after > %s)
                 AND (ta.depends_on IS NULL OR ta.depends_on IN
                      (SELECT id FROM task_assignment WHERE status='completed'))
                 ORDER BY ta.due_date""",
        (coachee_id, local_now, local_now),
    )
    tasks = c.fetchall()
    # Apply mail-merge to task descriptions
    for t in tasks:
        if t.get("task_desc"):
            t["task_desc"] = _merge_vars(t["task_desc"], coachee_id)
        if t.get("title"):
            t["title"] = _merge_vars(t["title"], coachee_id)
    return tasks



def _run_onboarding(coachee_id, coach_id, days_active):
    """Auto-deliver onboarding steps for new coachees (first 7 days)."""
    if days_active > 7:
        return
    c = db()
    c.execute(
        "SELECT * FROM onboarding_step WHERE coach_id=%s AND day_offset=%s",
        (coach_id, days_active),
    )
    steps = c.fetchall()
    local_today = datetime.now(ZoneInfo("UTC")).date().isoformat()
    for step in steps:
        # Assign task if template_id is set
        if step.get("template_id"):
            c.execute(
                "SELECT id FROM task_assignment WHERE template_id=%s AND coachee_id=%s AND due_date=%s",
                (step["template_id"], coachee_id, local_today),
            )
            if not c.fetchone():
                c.execute("SELECT task_unveil_time, task_freeze_time FROM coachee WHERE id=%s", (coachee_id,))
                cc = c.fetchone()
                vis = f"{local_today} {cc['task_unveil_time']}" if cc and cc["task_unveil_time"] else None
                frz = f"{local_today} {cc['task_freeze_time']}" if cc and cc["task_freeze_time"] else None
                c.execute(
                    "INSERT INTO task_assignment (template_id, coachee_id, due_date, visible_after, frozen_after) VALUES (%s,%s,%s,%s,%s)",
                    (step["template_id"], coachee_id, local_today, vis, frz),
                )
        # Send note if note_text is set
        if step.get("note_text"):
            from merge import _merge_vars
            note = _merge_vars(step["note_text"], coachee_id)
            # Avoid duplicate notes for same day/step
            c.execute(
                "SELECT id FROM note WHERE coachee_id=%s AND author_role='coach' AND content=%s AND DATE(created_at)=%s",
                (coachee_id, note, local_today),
            )
            if not c.fetchone():
                c.execute(
                    "INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coach',%s)",
                    (coachee_id, note),
                )
