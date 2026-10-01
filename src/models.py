"""SQLAlchemy Core table definitions for DSCoaching (30 tables).

Used by: database.py::init_db() (metadata.create_all — this is what
provisions a fresh DB) and migrations/env.py (Alembic target_metadata).
Every table below is annotated with which screen(s)/route(s) read or write
it, so a change here can be traced forward to the UI it affects.
"""

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.sql import func

metadata = MetaData()

# The authority account. Read/written by: auth.py (login/register/setup), routes_coach.py (settings/branding/dashboard), routes_admin.py (admin coach list/add/delete).
coach = Table(
    "coach",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(100), unique=True, nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("name", String(200), nullable=False),
    Column("timezone", String(64), server_default="Europe/London"),
    Column("logo_path", String(500)),
    Column("accent_color", String(20), server_default="#e94560"),
    Column("bg_color", String(20), server_default="#1a1a2e"),
    Column("card_color", String(20), server_default="#16213e"),
    Column("telegram_bot_token", String(200)),
    Column("is_admin", SmallInteger, server_default="0"),
    Column("status", String(20), server_default="active"),
    Column("email", String(200)),
    Column("features", JSON),
    Column("font_pref", String(20), server_default="clean"),
    Column("created_at", DateTime, server_default=func.now()),
)

# The person being coached. Read/written by: auth.py (login), routes_coach.py (add/edit/view coachee — coach's main screens), routes_coachee.py (the coachee's own /me dashboard + settings).
coachee = Table(
    "coachee",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(100), unique=True, nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("name", String(200), nullable=False),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("contract_text", Text),
    Column("safe_word", String(100), server_default="RED"),
    Column("status", String(20), server_default="active"),
    Column("task_unveil_time", Time, server_default="08:00:00"),
    Column("task_freeze_time", Time, server_default="22:00:00"),
    Column("timezone", String(64), server_default="Europe/London"),
    Column("context_text", Text),
    Column("strikes", Integer, server_default="0"),
    Column("avatar", String(50), server_default="🐕"),
    Column("color_scheme", String(20), server_default="#e94560"),
    Column("telegram_chat_id", String(100)),
    Column("features", JSON),
    Column("current_streak", Integer, server_default="0"),
    Column("best_streak", Integer, server_default="0"),
    Column("last_streak_date", Date),
    Column("login_count", Integer, server_default="0"),
    Column("font_pref", String(20), server_default="clean"),
    Column("created_at", DateTime, server_default=func.now()),
)

# Reusable task definition a coach creates once. Written by: routes_coach.py /coach/tasks (manage_tasks.html). Read by: tasks.py's assignment engine (recurring/reserve/week-plan/onboarding) to spawn task_assignment rows.
task_template = Table(
    "task_template",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("title", String(300), nullable=False),
    Column("description", Text),
    Column("recurrence", String(20), server_default="once"),
    Column("category", String(20), server_default="mental"),
    Column("difficulty", String(20), server_default="medium"),
    Column("is_reserve", SmallInteger, server_default="0"),
    Column("recur_days", Integer),
    Column("recur_approx", SmallInteger, server_default="0"),
    Column("in_library", SmallInteger, server_default="0"),
    Column("auto_grade", SmallInteger, server_default="0"),
    Column("photo_validate", SmallInteger, server_default="0"),
    Column("tags", String(500)),
    Column("created_at", DateTime, server_default=func.now()),
)

# One occurrence of a task for one coachee. Written by: tasks.py (auto-assignment, freeze/miss detection), routes_coach.py (manual assign, grading), routes_coachee.py (coachee's complete_task). Read by: coachee_dashboard.html (task list) and coach_view_coachee.html (grading queue).
task_assignment = Table(
    "task_assignment",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("template_id", Integer, ForeignKey("task_template.id"), nullable=False),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("due_date", Date),
    Column("status", String(20), server_default="pending"),
    Column("visible_after", DateTime),
    Column("frozen_after", DateTime),
    Column("response", Text),
    Column("responded_at", DateTime),
    Column("grade", String(1)),
    Column("coach_comment", Text),
    Column("attachment_path", String(500)),
    Column("reflection_rating", SmallInteger),
    Column("reflection_text", Text),
    Column("depends_on", Integer),
    Column("photo_validation_result", Text),
    Column("photo_validation_override", Text),
    Column("created_at", DateTime, server_default=func.now()),
)

# Immutable morning/evening/weekly check-in log. Written by: routes_coachee.py (coachee submits from /me). Read by: routes_coach.py (coach_view_coachee.html history) and automation.py (engagement scoring).
checkin = Table(
    "checkin",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("checkin_type", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

# Positive/negative note logged by the coach about a coachee. Written+read by: routes_coach.py (coach_view_coachee.html 'Ack' panel).
acknowledgement = Table(
    "acknowledgement",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("ack_type", String(20), nullable=False),
    Column("description", String(500), nullable=False),
    Column("notes", Text),
    Column("created_at", DateTime, server_default=func.now()),
)

# Food/hydration/alcohol/exercise/emotional entries. Written by: routes_coachee.py (/me tracking widgets). Read by: routes_coach.py (coach_view_coachee.html) and automation.py (mood/engagement signals).
tracking_log = Table(
    "tracking_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("category", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

# Async coach<->coachee message (also used for scheduled/pinned notes). Written+read by: routes_coach.py and routes_coachee.py (both dashboards' notes panel); auto-created by automation.py (auto_rule notifications) and tasks.py (miss/reserve notices).
note = Table(
    "note",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("author_role", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("pinned", SmallInteger, server_default="0"),
    Column("scheduled_at", DateTime),
    Column("read_at", DateTime),
    Column("created_at", DateTime, server_default=func.now()),
)

# Daily prompt authored by the coach (shared or per-coachee). Written by: routes_coach.py (manage_conditioning.html). Read by: routes_coachee.py (coachee's /me prompt-of-the-day).
mental_conditioning = Table(
    "mental_conditioning",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("prompt_date", Date, nullable=False),
    Column("prompt_text", Text, nullable=False),
    Column("target", String(20), server_default="all"),
    Column("coachee_id", Integer, ForeignKey("coachee.id")),
    Column("created_at", DateTime, server_default=func.now()),
)

# Coachee's answer to a mental_conditioning prompt. Written by: routes_coachee.py. Read by: routes_coach.py (coach_view_coachee.html).
mental_conditioning_response = Table(
    "mental_conditioning_response",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("conditioning_id", Integer, ForeignKey("mental_conditioning.id"), nullable=False),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

# AI-generated profile text for a coachee (ai.py::_build_profile_prompt). Written+read by: routes_coach.py (coach_view_coachee.html 'Profile' panel) only — never shown to the coachee.
psychological_profile = Table(
    "psychological_profile",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), unique=True, nullable=False),
    Column("profile_text", Text),
    Column("updated_at", DateTime, server_default=func.now()),
)

# Immutable version history of coachee.contract_text. Written by: routes_coach.py whenever the contract is edited. Read by: contract_history.html.
contract_history = Table(
    "contract_history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("contract_text", Text, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

# Best-effort action trail (helpers.py::_audit, swallows its own errors — BUG-005/H3). Written by: nearly every route via _audit(). Read by: routes_admin.py (audit_log.html) only.
audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("role", String(20), nullable=False),
    Column("action", String(100), nullable=False),
    Column("ip", String(45)),
    Column("user_agent", String(500)),
    Column("created_at", DateTime, server_default=func.now()),
)

# One row per coachee per ISO week, AI or coach-authored recap. Written+read by: routes_coach.py (weekly_summary.html).
weekly_summary = Table(
    "weekly_summary",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("week_start", Date, nullable=False),
    Column("summary_text", Text),
    Column("created_at", DateTime, server_default=func.now()),
    UniqueConstraint("coachee_id", "week_start"),
)

# Audio message (coach<->coachee), file stored under ATTACHMENTS_DIR. Written+read by: routes_coach.py and routes_coachee.py dashboards, alongside `note`.
voice_note = Table(
    "voice_note",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("author_role", String(20), nullable=False),
    Column("file_path", String(500), nullable=False),
    Column("duration_sec", Integer),
    Column("created_at", DateTime, server_default=func.now()),
)

# Coachee-proposed goal, coach approves/rejects. Written by: routes_coachee.py (propose) and routes_coach.py (approve/reject/comment). Read by both dashboards.
goal = Table(
    "goal",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("title", String(300), nullable=False),
    Column("description", Text),
    Column("status", String(20), server_default="proposed"),
    Column("coach_notes", Text),
    Column("created_at", DateTime, server_default=func.now()),
)

# Coachee's journal entry; visible_to_coach controls whether routes_coach.py's view can see it. Written by: routes_coachee.py.
journal = Table(
    "journal",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("content", Text, nullable=False),
    Column("visible_to_coach", SmallInteger, server_default="0"),
    Column("created_at", DateTime, server_default=func.now()),
)

# Coachee-uploaded progress photo, file stored under ATTACHMENTS_DIR. Written by: routes_coachee.py. Read by: routes_coach.py (coach_view_coachee.html gallery).
progress_photo = Table(
    "progress_photo",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("file_path", String(500), nullable=False),
    Column("caption", String(500)),
    Column("created_at", DateTime, server_default=func.now()),
)

# Coach's message to the app admin (bug reports/help requests). Written by: routes_coach.py (coach_support.html). Read+replied by: routes_admin.py (admin_support.html).
support_message = Table(
    "support_message",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("message", Text, nullable=False),
    Column("recent_actions", Text),
    Column("status", String(20), server_default="open"),
    Column("admin_reply", Text),
    Column("created_at", DateTime, server_default=func.now()),
)


# ── New tables: LLM-suggested features ──

# Earned milestone badge (streak thresholds etc). Written by: automation.py (streak-milestone check). Read by: routes_coach.py (coach_view_coachee.html) and coachee_dashboard.html.
badge = Table(
    "badge",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("badge_type", String(50), nullable=False),
    Column("badge_name", String(200), nullable=False),
    Column("description", String(500)),
    Column("icon", String(50)),
    Column("created_at", DateTime, server_default=func.now()),
)

# Recurring ritual definition (shared or per-coachee), separate from task_template. Written by: routes_coach.py (manage_rituals.html). Read by: automation.py (miss detection) and both dashboards.
ritual = Table(
    "ritual",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("coachee_id", Integer, ForeignKey("coachee.id")),
    Column("name", String(200), nullable=False),
    Column("description", Text),
    Column("schedule", String(50), server_default="daily"),
    Column("schedule_days", String(50)),
    Column("active", SmallInteger, server_default="1"),
    Column("created_at", DateTime, server_default=func.now()),
)

# One completion record per ritual per coachee per day. Written by: routes_coachee.py (ritual complete action). Read by: automation.py (streaks) and both dashboards.
ritual_log = Table(
    "ritual_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ritual_id", Integer, ForeignKey("ritual.id"), nullable=False),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("completed_date", Date, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
    UniqueConstraint("ritual_id", "coachee_id", "completed_date"),
)


# Coach-configured trigger->action automation (e.g. task_missed -> send note). Written by: routes_coach.py (manage_automations.html). Read+executed by: automation.py::_run_auto_rules(), called from the coachee dashboard load path.
auto_rule = Table(
    "auto_rule",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("name", String(200), nullable=False),
    Column("trigger", String(50), nullable=False),
    Column("condition_field", String(50)),
    Column("condition_op", String(10)),
    Column("condition_value", String(100)),
    Column("action_type", String(50), nullable=False),
    Column("action_template", Text, nullable=False),
    Column("active", SmallInteger, server_default="1"),
    Column("created_at", DateTime, server_default=func.now()),
)


# Recurring weekly schedule entry (day_of_week -> template). Written by: routes_coach.py (week_plan.html). Read by: tasks.py's assignment engine.
week_plan = Table(
    "week_plan",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("day_of_week", SmallInteger, nullable=False),
    Column("template_id", Integer, ForeignKey("task_template.id"), nullable=False),
    Column("coachee_id", Integer, ForeignKey("coachee.id")),
    Column("created_at", DateTime, server_default=func.now()),
)

# Day-offset task/note scheduled for a coachee's first N days. Written by: routes_coach.py (onboarding.html). Read by: tasks.py::_run_onboarding().
onboarding_step = Table(
    "onboarding_step",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("day_offset", SmallInteger, nullable=False),
    Column("template_id", Integer, ForeignKey("task_template.id")),
    Column("note_text", Text),
    Column("created_at", DateTime, server_default=func.now()),
)


# Recurring payment arrangement for a coachee. Written+read by: routes_coach.py (payments.html).
payment_plan = Table(
    "payment_plan",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), unique=True, nullable=False),
    Column("frequency", String(20), nullable=False),
    Column("amount", String(50), nullable=False),
    Column("currency", String(10), server_default="EUR"),
    Column("start_date", Date, nullable=False),
    Column("active", SmallInteger, server_default="1"),
    Column("created_at", DateTime, server_default=func.now()),
)

# One confirmed payment record. Written+read by: routes_coach.py (payments.html) and automation.py (payment reminders).
payment_log = Table(
    "payment_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("amount", String(50), nullable=False),
    Column("currency", String(10), server_default="EUR"),
    Column("period_start", Date),
    Column("period_end", Date),
    Column("confirmed_at", DateTime, server_default=func.now()),
    Column("notes", String(500)),
    Column("created_at", DateTime, server_default=func.now()),
)


# ── Creative Works Archive ──

# A themed set of creative-writing submissions for one coachee. Written+read by: routes_coach.py (coach_writing.html) and routes_coachee.py (writing.html).
creative_collection = Table(
    "creative_collection",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("title", String(300), nullable=False),
    Column("description", Text),
    Column("status", String(20), server_default="active"),
    Column("created_at", DateTime, server_default=func.now()),
)

# Coach-assigned writing prompt/constraint (subject, form, word count, etc). Written by: routes_coach.py. Read by: routes_coachee.py (writing.html) when the coachee starts a new piece.
creative_constraint = Table(
    "creative_constraint",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coach_id", Integer, ForeignKey("coach.id"), nullable=False),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("constraint_type", String(30), nullable=False),
    Column("constraint_value", Text, nullable=False),
    Column("active_date", Date),
    Column("used", SmallInteger, server_default="0"),
    Column("created_at", DateTime, server_default=func.now()),
)

# One submitted piece of creative writing. Written by: routes_coachee.py (writing.html submit). Read+annotated by: routes_coach.py (coach_writing.html, writing_view.html).
creative_work = Table(
    "creative_work",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("collection_id", Integer, ForeignKey("creative_collection.id")),
    Column("constraint_id", Integer, ForeignKey("creative_constraint.id")),
    Column("title", String(300)),
    Column("content", Text, nullable=False),
    Column("work_type", String(30), server_default="poem"),
    Column("tags", String(500)),
    Column("coach_notes", Text),
    Column("selected_for_final", SmallInteger, server_default="0"),
    Column("created_at", DateTime, server_default=func.now()),
)
