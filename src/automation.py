"""Automation engine: rules, badges, reports, engagement scoring, rituals, levels."""

import json
from datetime import date, datetime, timedelta

from helpers import db
from merge import _get_merge_context, _merge_vars


def _run_auto_rules(coachee_id, trigger, context=None):
    """Execute automation rules for a given trigger event.

    PURPOSE: Evaluate the coach's active auto_rule rows for a trigger, check conditions, and run actions (send_note, award_badge, assign_task).
    CALLED BY: routes_coachee.py on checkin submit (POST /me/checkin, trigger 'checkin_submitted') and task complete (POST /me/task/<tid>, trigger 'task_completed'); tasks.py _freeze_overdue ('task_missed') and _update_streak ('streak_milestone') during GET /me — serves coachee dashboard/action screens.
    WHEN: On coachee check-in/task submit and during coachee dashboard load when tasks are missed or a streak milestone is hit.
    """
    c = db()
    c.execute("SELECT coach_id FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    if not row:
        return
    coach_id = row["coach_id"]

    c.execute(
        "SELECT * FROM auto_rule WHERE coach_id=%s AND trigger=%s AND active=1",
        (coach_id, trigger),
    )
    rules = c.fetchall()
    if not rules:
        return

    # Get coachee data for condition evaluation
    c.execute("SELECT * FROM coachee WHERE id=%s", (coachee_id,))
    coachee = c.fetchone()
    if not coachee:
        return

    merge_ctx = _get_merge_context(coachee_id)

    for rule in rules:
        # Evaluate condition
        if rule["condition_field"] and rule["condition_op"] and rule["condition_value"]:
            field_val = merge_ctx.get(rule["condition_field"], "0")
            try:
                field_num = float(field_val) if field_val.replace(".", "").replace("-", "").isdigit() else 0
                target_num = float(rule["condition_value"])
                op = rule["condition_op"]
                if op == ">=" and not (field_num >= target_num):
                    continue
                elif op == "<=" and not (field_num <= target_num):
                    continue
                elif op == ">" and not (field_num > target_num):
                    continue
                elif op == "<" and not (field_num < target_num):
                    continue
                elif op == "==" and not (field_num == target_num):
                    continue
                elif op == "!=" and not (field_num != target_num):
                    continue
            except (ValueError, TypeError):
                continue

        # Execute action
        action_text = _merge_vars(rule["action_template"], coachee_id)
        if rule["action_type"] == "send_note":
            c.execute(
                "INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coach',%s)",
                (coachee_id, action_text),
            )
        elif rule["action_type"] == "award_badge":
            badge_type = f"rule_{rule['id']}_{date.today().isoformat()}"
            c.execute(
                "SELECT id FROM badge WHERE coachee_id=%s AND badge_type=%s", (coachee_id, badge_type)
            )
            if not c.fetchone():
                c.execute(
                    "INSERT INTO badge (coachee_id, badge_type, badge_name, description, icon) VALUES (%s,%s,%s,%s,%s)",
                    (coachee_id, badge_type, rule["name"], action_text, "\U0001f3c5"),
                )
        elif rule["action_type"] == "assign_task":
            # action_template should be a task template ID
            try:
                tmpl_id = int(action_text.strip())
                today = date.today().isoformat()
                c.execute(
                    "SELECT id FROM task_assignment WHERE template_id=%s AND coachee_id=%s AND due_date=%s",
                    (tmpl_id, coachee_id, today),
                )
                if not c.fetchone():
                    c.execute(
                        "INSERT INTO task_assignment (template_id, coachee_id, due_date) VALUES (%s,%s,%s)",
                        (tmpl_id, coachee_id, today),
                    )
            except (ValueError, TypeError):
                pass


def _auto_escalation_note(coachee_id, missed_count):
    """Send an auto-escalation note when tasks are missed.

    PURPOSE: Insert a coach->coachee note (from the coach's escalation template or a default) after missed tasks, merging in name/strikes/missed count.
    CALLED BY: tasks.py _freeze_overdue, which runs from routes_coachee.py coachee_dashboard (GET /me) — the note then appears on the coachee dashboard/notes screen.
    WHEN: On coachee dashboard load, when _freeze_overdue detects one or more newly missed tasks.
    """
    c = db()
    c.execute("SELECT coach_id FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    if not row:
        return
    # Check if coach has configured an escalation template
    c.execute("SELECT features FROM coach WHERE id=%s", (row["coach_id"],))
    coach_row = c.fetchone()
    features = json.loads(coach_row["features"]) if coach_row and coach_row["features"] and isinstance(coach_row["features"], str) else (coach_row["features"] if coach_row and isinstance(coach_row.get("features"), dict) else {})
    template = features.get("escalation_template", "")
    if not template:
        template = "{{name}}, you missed {{strikes}} task(s) today. Your streak has been reset. Tomorrow is a new opportunity to demonstrate your commitment."
    # Add missed count to merge context temporarily
    text = _merge_vars(template, coachee_id)
    text = text.replace("{{missed}}", str(missed_count))
    c.execute(
        "INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coach',%s)",
        (coachee_id, text),
    )


def _streak_milestone_note(coachee_id, new_streak):
    """Send a congratulatory note when streak hits a milestone.

    PURPOSE: Insert a coach->coachee note at 7/14/30/60/90-day streaks (coach custom template or default), returning early otherwise.
    CALLED BY: tasks.py _update_streak, which runs from routes_coachee.py coachee_dashboard (GET /me) — the note appears on the coachee dashboard/notes screen.
    WHEN: On coachee dashboard load, when _update_streak advances the streak onto a milestone value.
    """
    milestones = {
        7: "\U0001f525 One week, {{name}}! 7 days of consistent discipline. You've proven you can sustain this. Keep building.",
        14: "\u26a1 Two weeks, {{name}}! 14 days of unwavering commitment. Your dedication is impressive. The next level awaits.",
        30: "\U0001f48e One month, {{name}}! 30 consecutive days of excellence. You've transformed routine into identity. Extraordinary.",
        60: "\U0001f451 Two months, {{name}}! 60 days of absolute discipline. You are a force of nature. I'm proud of what you've become.",
        90: "\u2728 Three months, {{name}}! 90 days \u2014 you've transcended. This isn't discipline anymore. This is who you are.",
    }
    if new_streak not in milestones:
        return
    c = db()
    c.execute("SELECT coach_id FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    if not row:
        return
    # Check if coach has custom milestone templates
    c.execute("SELECT features FROM coach WHERE id=%s", (row["coach_id"],))
    coach_row = c.fetchone()
    features = json.loads(coach_row["features"]) if coach_row and coach_row["features"] and isinstance(coach_row["features"], str) else (coach_row["features"] if coach_row and isinstance(coach_row.get("features"), dict) else {})
    custom = features.get(f"milestone_{new_streak}", "")
    template = custom if custom else milestones[new_streak]
    text = _merge_vars(template, coachee_id)
    c.execute(
        "INSERT INTO note (coachee_id, author_role, content) VALUES (%s,'coach',%s)",
        (coachee_id, text),
    )


def _check_and_award_badges(coachee_id):
    """Check badge conditions and award new badges.

    PURPOSE: Evaluate streak, perfect-week grades, and first-check-in conditions and insert any newly earned badge rows.
    CALLED BY: routes_coachee.py coachee_dashboard (GET /me) — earned badges are then shown via _get_badges on the coachee dashboard screen.
    WHEN: On coachee dashboard load, after streak/freeze processing.
    """
    c = db()
    c.execute("SELECT badge_type FROM badge WHERE coachee_id=%s", (coachee_id,))
    existing = {r["badge_type"] for r in c.fetchall()}

    c.execute("SELECT current_streak, best_streak FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    streak = row["current_streak"] or 0
    best = row["best_streak"] or 0
    max_streak = max(streak, best)

    badges_to_award = []
    if max_streak >= 7 and "streak_7" not in existing:
        badges_to_award.append(("streak_7", "\U0001f525 Week Warrior", "7-day streak achieved", "\U0001f525"))
    if max_streak >= 14 and "streak_14" not in existing:
        badges_to_award.append(("streak_14", "\u26a1 Fortnight Force", "14-day streak achieved", "\u26a1"))
    if max_streak >= 30 and "streak_30" not in existing:
        badges_to_award.append(("streak_30", "\U0001f48e Diamond Discipline", "30-day streak achieved", "\U0001f48e"))

    # Check if all tasks graded A in last 7 days (min 3 tasks)
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    c.execute(
        "SELECT grade FROM task_assignment WHERE coachee_id=%s AND grade IS NOT NULL AND responded_at >= %s",
        (coachee_id, week_ago),
    )
    recent_grades = [r["grade"] for r in c.fetchall()]
    if len(recent_grades) >= 3 and all(g == "A" for g in recent_grades) and "perfect_week" not in existing:
        badges_to_award.append(("perfect_week", "\U0001f31f Perfect Week", "All tasks graded A in a week", "\U0001f31f"))

    # First check-in badge
    c.execute("SELECT COUNT(*) as cnt FROM checkin WHERE coachee_id=%s", (coachee_id,))
    if c.fetchone()["cnt"] >= 1 and "first_checkin" not in existing:
        badges_to_award.append(("first_checkin", "\U0001f4dd First Steps", "Completed first check-in", "\U0001f4dd"))

    for btype, bname, desc, icon in badges_to_award:
        c.execute(
            "INSERT INTO badge (coachee_id, badge_type, badge_name, description, icon) VALUES (%s,%s,%s,%s,%s)",
            (coachee_id, btype, bname, desc, icon),
        )


def _get_badges(coachee_id):
    """Get all badges for a coachee.

    PURPOSE: Fetch the coachee's earned badges (newest first) for display.
    CALLED BY: routes_coachee.py coachee_dashboard (GET /me), passed as earned_badges into coachee_dashboard.html — serves the coachee dashboard screen.
    WHEN: On coachee dashboard load.
    """
    c = db()
    c.execute("SELECT * FROM badge WHERE coachee_id=%s ORDER BY created_at DESC", (coachee_id,))
    return c.fetchall()


def _mood_sparkline(coachee_id):
    """Get last 14 days of mood ratings from check-ins.

    PURPOSE: Return (date, mood) points from the past 14 days for a small trend chart (empty list on error).
    CALLED BY: routes_coachee.py coachee_dashboard (GET /me), passed as mood_data into coachee_dashboard.html — serves the coachee dashboard screen.
    WHEN: On coachee dashboard load.
    """
    c = db()
    fourteen_ago = (date.today() - timedelta(days=14)).isoformat()
    try:
        c.execute(
            "SELECT DATE(created_at) as d, mood FROM checkin WHERE coachee_id=%s AND mood IS NOT NULL AND DATE(created_at) >= %s ORDER BY created_at",
            (coachee_id, fourteen_ago),
        )
        return c.fetchall()
    except Exception:
        return []


def _engagement_score(coachee_id):
    """Compute 7-day engagement score (0-100).

    PURPOSE: Weighted blend of 7-day check-in rate (30%), task completion (50%), and tracking frequency (20%).
    CALLED BY: routes_coach.py coach_dashboard (GET /coach), set as cc["engagement"] per coachee — serves the coach dashboard screen.
    WHEN: On coach dashboard load, computed for each listed coachee.
    """
    c = db()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    # Check-in rate (max 14 check-ins = morning + evening * 7 days)
    c.execute(
        "SELECT COUNT(*) as cnt FROM checkin WHERE coachee_id=%s AND DATE(created_at) >= %s",
        (coachee_id, week_ago),
    )
    checkins = min(c.fetchone()["cnt"], 14)
    checkin_score = checkins / 14 * 100

    # Task completion rate
    c.execute(
        "SELECT COUNT(*) as total, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done FROM task_assignment WHERE coachee_id=%s AND due_date >= %s",
        (coachee_id, week_ago),
    )
    row = c.fetchone()
    task_score = (row["done"] or 0) / row["total"] * 100 if row["total"] else 50

    # Tracking frequency (target: 3/day = 21/week)
    c.execute(
        "SELECT COUNT(*) as cnt FROM tracking_log WHERE coachee_id=%s AND DATE(created_at) >= %s",
        (coachee_id, week_ago),
    )
    tracking = min(c.fetchone()["cnt"], 21)
    tracking_score = tracking / 21 * 100

    return round((checkin_score * 0.3 + task_score * 0.5 + tracking_score * 0.2))


def _completion_hours(coachee_id):
    """Get hour distribution of task completions.

    PURPOSE: Build a 24-slot histogram of the hours at which the coachee completed tasks.
    CALLED BY: routes_coach.py coach-view-coachee (GET /coach/coachee/<cid>), passed as completion_hours into coach_view_coachee.html — serves the coach's per-coachee detail screen.
    WHEN: On load of the coach's individual coachee view.
    """
    c = db()
    c.execute(
        "SELECT responded_at FROM task_assignment WHERE coachee_id=%s AND responded_at IS NOT NULL",
        (coachee_id,),
    )
    hours = [0] * 24
    for r in c.fetchall():
        ts = r["responded_at"]
        if ts:
            if isinstance(ts, str):
                try:
                    h = int(ts.split(" ")[1].split(":")[0])
                    hours[h] += 1
                except (IndexError, ValueError):
                    pass
            elif hasattr(ts, "hour"):
                hours[ts.hour] += 1
    return hours


def _get_rituals(coachee_id, coach_id):
    """Get active rituals for a coachee.

    PURPOSE: Fetch active ritual definitions that apply to this coachee (shared or per-coachee) for the given coach.
    CALLED BY: routes_coachee.py coachee_dashboard (GET /me), used for the rituals list and to feed _ritual_status_today — serves the coachee dashboard screen.
    WHEN: On coachee dashboard load.
    """
    c = db()
    c.execute(
        "SELECT * FROM ritual WHERE (coachee_id=%s OR coachee_id IS NULL) AND coach_id=%s AND active=1",
        (coachee_id, coach_id),
    )
    return c.fetchall()


def _ritual_status_today(coachee_id, rituals, today_str):
    """Check which rituals are completed today.

    PURPOSE: Return the set of ritual_ids the coachee has logged as done for today.
    CALLED BY: routes_coachee.py coachee_dashboard (GET /me), passed as rituals_done into coachee_dashboard.html — serves the coachee dashboard screen.
    WHEN: On coachee dashboard load, alongside _get_rituals.
    """
    c = db()
    completed_ids = set()
    if rituals:
        c.execute(
            "SELECT ritual_id FROM ritual_log WHERE coachee_id=%s AND completed_date=%s",
            (coachee_id, today_str),
        )
        completed_ids = {r["ritual_id"] for r in c.fetchall()}
    return completed_ids


def _compute_level(coachee_id, coach_id):
    """Compute training level from streak data and coach config.

    PURPOSE: Derive current/next training level (Initiate→Transcendent) and progress % from the coachee's best streak.
    CALLED BY: routes_coachee.py coachee_dashboard (GET /me), passed as level_info into coachee_dashboard.html — serves the coachee dashboard screen.
    WHEN: On coachee dashboard load.
    """
    c = db()
    c.execute("SELECT current_streak, best_streak FROM coachee WHERE id=%s", (coachee_id,))
    row = c.fetchone()
    best_streak = max(row["current_streak"] or 0, row["best_streak"] or 0)

    # Default levels (coach can customize via features JSON in future)
    levels = [
        {"name": "Initiate", "threshold": 0, "icon": "\U0001f331"},
        {"name": "Dedicated", "threshold": 7, "icon": "\U0001f525"},
        {"name": "Disciplined", "threshold": 14, "icon": "\u26a1"},
        {"name": "Devoted", "threshold": 30, "icon": "\U0001f48e"},
        {"name": "Exemplary", "threshold": 60, "icon": "\U0001f451"},
        {"name": "Transcendent", "threshold": 90, "icon": "\u2728"},
    ]

    current_level = levels[0]
    next_level = levels[1] if len(levels) > 1 else None
    for i, lv in enumerate(levels):
        if best_streak >= lv["threshold"]:
            current_level = lv
            next_level = levels[i + 1] if i + 1 < len(levels) else None

    progress = 0
    if next_level:
        range_size = next_level["threshold"] - current_level["threshold"]
        progress = min(100, round((best_streak - current_level["threshold"]) / range_size * 100)) if range_size else 100
    else:
        progress = 100

    return {"current": current_level, "next": next_level, "progress": progress, "best_streak": best_streak}


def _weekly_report(coachee_id):
    """Compute weekly report card from existing data.

    PURPOSE: Aggregate the last 7 days into avg grade, task compliance, check-in rate, and tracking count.
    CALLED BY: routes_coachee.py coachee_dashboard (GET /me, weekly_report into coachee_dashboard.html) and routes_coach.py weekly_summary (GET /coach/coachee/<cid>/summary) — serves the coachee dashboard and the coach weekly-summary screens.
    WHEN: On coachee dashboard load and on coach weekly-summary view.
    """
    c = db()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    # Grade average
    c.execute(
        "SELECT grade FROM task_assignment WHERE coachee_id=%s AND grade IS NOT NULL AND responded_at >= %s",
        (coachee_id, week_ago),
    )
    grades = [r["grade"] for r in c.fetchall()]
    grade_map = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}
    avg_grade_num = sum(grade_map.get(g, 4) for g in grades) / len(grades) if grades else 0
    avg_grade = next((k for k, v in grade_map.items() if v >= round(avg_grade_num)), "\u2014") if grades else "\u2014"

    # Compliance: completed / (completed + missed)
    c.execute(
        "SELECT status FROM task_assignment WHERE coachee_id=%s AND due_date >= %s AND status IN ('completed','missed','partial')",
        (coachee_id, week_ago),
    )
    statuses = [r["status"] for r in c.fetchall()]
    completed = sum(1 for s in statuses if s == "completed")
    compliance = round(completed * 100 / len(statuses)) if statuses else 0

    # Check-in consistency
    c.execute(
        "SELECT DATE(created_at) as d, checkin_type FROM checkin WHERE coachee_id=%s AND DATE(created_at) >= %s",
        (coachee_id, week_ago),
    )
    checkin_days = set()
    for r in c.fetchall():
        checkin_days.add(str(r["d"]))
    checkin_rate = round(len(checkin_days) * 100 / 7)

    # Tracking frequency
    c.execute(
        "SELECT COUNT(*) as cnt FROM tracking_log WHERE coachee_id=%s AND DATE(created_at) >= %s",
        (coachee_id, week_ago),
    )
    tracking_count = c.fetchone()["cnt"]

    return {
        "avg_grade": avg_grade,
        "compliance": compliance,
        "checkin_rate": min(checkin_rate, 100),
        "tracking_count": tracking_count,
        "tasks_graded": len(grades),
        "tasks_total": len(statuses),
    }



def _payment_compliance(coachee_id):
    """Compute payment compliance status for a coachee.

    PURPOSE: Compare expected vs actual payments against the active plan and return a status (green/yellow/orange/red/none) with periods_late.
    CALLED BY: routes_coach.py coach_dashboard (GET /coach, set as cc["payment"]) and the coach payments route (GET /coach/.../payments) — serves the coach dashboard and coach payments screens.
    WHEN: On coach dashboard load and on the coach payments screen load.

    Returns: dict with status (green/yellow/orange/red/none), periods_late, last_payment, plan info.
    """
    c = db()
    # Get payment plan
    c.execute("SELECT * FROM payment_plan WHERE coachee_id=%s AND active=1", (coachee_id,))
    plan = c.fetchone()
    if not plan:
        return {"status": "none", "periods_late": 0, "plan": None, "last_payment": None}

    # Get last payment
    c.execute(
        "SELECT * FROM payment_log WHERE coachee_id=%s ORDER BY confirmed_at DESC LIMIT 1",
        (coachee_id,),
    )
    last_payment = c.fetchone()

    from datetime import date as _date, timedelta
    today = _date.today()
    freq = plan["frequency"]
    start = plan["start_date"]
    if isinstance(start, str):
        from datetime import datetime as _dt
        start = _dt.fromisoformat(start).date()

    # Compute how many periods should have been paid since start_date
    if freq == "daily":
        period_days = 1
    elif freq == "weekly":
        period_days = 7
    elif freq == "monthly":
        period_days = 30
    elif freq == "adhoc":
        # Ad-hoc: no strict schedule, just check if ever paid
        if last_payment:
            return {"status": "green", "periods_late": 0, "plan": plan, "last_payment": last_payment}
        else:
            days_since_start = (today - start).days
            if days_since_start <= 7:
                return {"status": "green", "periods_late": 0, "plan": plan, "last_payment": None}
            elif days_since_start <= 14:
                return {"status": "yellow", "periods_late": 1, "plan": plan, "last_payment": None}
            else:
                return {"status": "orange", "periods_late": 2, "plan": plan, "last_payment": None}
    else:
        period_days = 30  # fallback

    if freq != "adhoc":
        # Count expected payments
        days_active = (today - start).days
        expected_periods = max(1, days_active // period_days)

        # Count actual payments
        c.execute("SELECT COUNT(*) as cnt FROM payment_log WHERE coachee_id=%s", (coachee_id,))
        actual = c.fetchone()["cnt"]

        periods_late = max(0, expected_periods - actual)

        if periods_late == 0:
            status = "green"
        elif periods_late == 1:
            status = "yellow"
        elif periods_late == 2:
            status = "orange"
        else:
            status = "red"

        return {"status": status, "periods_late": periods_late, "plan": plan, "last_payment": last_payment}

    return {"status": "none", "periods_late": 0, "plan": plan, "last_payment": last_payment}
