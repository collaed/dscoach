"""SQLAlchemy Core table definitions for DSCoaching (20 tables)."""

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

checkin = Table(
    "checkin",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("checkin_type", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

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

tracking_log = Table(
    "tracking_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("category", String(20), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

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

mental_conditioning_response = Table(
    "mental_conditioning_response",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("conditioning_id", Integer, ForeignKey("mental_conditioning.id"), nullable=False),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

psychological_profile = Table(
    "psychological_profile",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), unique=True, nullable=False),
    Column("profile_text", Text),
    Column("updated_at", DateTime, server_default=func.now()),
)

contract_history = Table(
    "contract_history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("contract_text", Text, nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)

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

journal = Table(
    "journal",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("content", Text, nullable=False),
    Column("visible_to_coach", SmallInteger, server_default="0"),
    Column("created_at", DateTime, server_default=func.now()),
)

progress_photo = Table(
    "progress_photo",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("coachee_id", Integer, ForeignKey("coachee.id"), nullable=False),
    Column("file_path", String(500), nullable=False),
    Column("caption", String(500)),
    Column("created_at", DateTime, server_default=func.now()),
)

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
