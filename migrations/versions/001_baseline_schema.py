"""baseline_schema

Revision ID: 001
Revises:
Create Date: 2026-08-23

This migration represents the existing production schema (27 tables).
It should be STAMPED (not run) on existing databases:
    alembic stamp 001

For new databases, it creates the full schema from scratch.
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables for a fresh database."""
    op.create_table(
        "coach",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), server_default="Europe/London"),
        sa.Column("logo_path", sa.String(500)),
        sa.Column("accent_color", sa.String(20), server_default="#e94560"),
        sa.Column("bg_color", sa.String(20), server_default="#1a1a2e"),
        sa.Column("card_color", sa.String(20), server_default="#16213e"),
        sa.Column("telegram_bot_token", sa.String(200)),
        sa.Column("is_admin", sa.SmallInteger(), server_default="0"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("email", sa.String(200)),
        sa.Column("features", sa.JSON()),
        sa.Column("font_pref", sa.String(20), server_default="clean"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "coachee",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("contract_text", sa.Text()),
        sa.Column("safe_word", sa.String(100), server_default="RED"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("task_unveil_time", sa.Time(), server_default="08:00:00"),
        sa.Column("task_freeze_time", sa.Time(), server_default="22:00:00"),
        sa.Column("timezone", sa.String(64), server_default="Europe/London"),
        sa.Column("context_text", sa.Text()),
        sa.Column("strikes", sa.Integer(), server_default="0"),
        sa.Column("avatar", sa.String(50), server_default=""),
        sa.Column("color_scheme", sa.String(20), server_default="#e94560"),
        sa.Column("telegram_chat_id", sa.String(100)),
        sa.Column("features", sa.JSON()),
        sa.Column("current_streak", sa.Integer(), server_default="0"),
        sa.Column("best_streak", sa.Integer(), server_default="0"),
        sa.Column("last_streak_date", sa.Date()),
        sa.Column("login_count", sa.Integer(), server_default="0"),
        sa.Column("font_pref", sa.String(20), server_default="clean"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "task_template",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("recurrence", sa.String(20), server_default="once"),
        sa.Column("category", sa.String(20), server_default="mental"),
        sa.Column("difficulty", sa.String(20), server_default="medium"),
        sa.Column("is_reserve", sa.SmallInteger(), server_default="0"),
        sa.Column("recur_days", sa.Integer()),
        sa.Column("recur_approx", sa.SmallInteger(), server_default="0"),
        sa.Column("in_library", sa.SmallInteger(), server_default="0"),
        sa.Column("auto_grade", sa.SmallInteger(), server_default="0"),
        sa.Column("photo_validate", sa.SmallInteger(), server_default="0"),
        sa.Column("tags", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "task_assignment",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("task_template.id"), nullable=False),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("visible_after", sa.DateTime()),
        sa.Column("frozen_after", sa.DateTime()),
        sa.Column("response", sa.Text()),
        sa.Column("responded_at", sa.DateTime()),
        sa.Column("grade", sa.String(1)),
        sa.Column("coach_comment", sa.Text()),
        sa.Column("attachment_path", sa.String(500)),
        sa.Column("reflection_rating", sa.SmallInteger()),
        sa.Column("reflection_text", sa.Text()),
        sa.Column("depends_on", sa.Integer()),
        sa.Column("photo_validation_result", sa.Text()),
        sa.Column("photo_validation_override", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "checkin",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("checkin_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "acknowledgement",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("ack_type", sa.String(20), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "tracking_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "note",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("author_role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("pinned", sa.SmallInteger(), server_default="0"),
        sa.Column("scheduled_at", sa.DateTime()),
        sa.Column("read_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "mental_conditioning",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("prompt_date", sa.Date(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("target", sa.String(20), server_default="all"),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "mental_conditioning_response",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conditioning_id", sa.Integer(), sa.ForeignKey("mental_conditioning.id"), nullable=False),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "psychological_profile",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), unique=True, nullable=False),
        sa.Column("profile_text", sa.Text()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "contract_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("contract_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("ip", sa.String(45)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "weekly_summary",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("summary_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("coachee_id", "week_start"),
    )
    op.create_table(
        "voice_note",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("author_role", sa.String(20), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("duration_sec", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "goal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), server_default="proposed"),
        sa.Column("coach_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "journal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("visible_to_coach", sa.SmallInteger(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "progress_photo",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("caption", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "support_message",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("recent_actions", sa.Text()),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("admin_reply", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "badge",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("badge_type", sa.String(50), nullable=False),
        sa.Column("badge_name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("icon", sa.String(50)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "ritual",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("schedule", sa.String(50), server_default="daily"),
        sa.Column("schedule_days", sa.String(50)),
        sa.Column("active", sa.SmallInteger(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "ritual_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ritual_id", sa.Integer(), sa.ForeignKey("ritual.id"), nullable=False),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("completed_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("ritual_id", "coachee_id", "completed_date"),
    )
    op.create_table(
        "auto_rule",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("trigger", sa.String(50), nullable=False),
        sa.Column("condition_field", sa.String(50)),
        sa.Column("condition_op", sa.String(10)),
        sa.Column("condition_value", sa.String(100)),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("action_template", sa.Text(), nullable=False),
        sa.Column("active", sa.SmallInteger(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "week_plan",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("task_template.id"), nullable=False),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "onboarding_step",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("day_offset", sa.SmallInteger(), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("task_template.id")),
        sa.Column("note_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "payment_plan",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), unique=True, nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("amount", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(10), server_default="EUR"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("active", sa.SmallInteger(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "payment_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("amount", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(10), server_default="EUR"),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("confirmed_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("notes", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "creative_collection",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "creative_constraint",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("constraint_type", sa.String(30), nullable=False),
        sa.Column("constraint_value", sa.Text(), nullable=False),
        sa.Column("active_date", sa.Date()),
        sa.Column("used", sa.SmallInteger(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "creative_work",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("creative_collection.id")),
        sa.Column("constraint_id", sa.Integer(), sa.ForeignKey("creative_constraint.id")),
        sa.Column("title", sa.String(300)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("work_type", sa.String(30), server_default="poem"),
        sa.Column("tags", sa.String(500)),
        sa.Column("coach_notes", sa.Text()),
        sa.Column("selected_for_final", sa.SmallInteger(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Drop all tables (dangerous — only for dev/test)."""
    tables = [
        "creative_work", "creative_constraint", "creative_collection",
        "payment_log", "payment_plan", "onboarding_step", "week_plan",
        "auto_rule", "ritual_log", "ritual", "badge", "support_message",
        "progress_photo", "journal", "goal", "voice_note", "weekly_summary",
        "audit_log", "contract_history", "psychological_profile",
        "mental_conditioning_response", "mental_conditioning", "note",
        "tracking_log", "acknowledgement", "checkin", "task_assignment",
        "task_template", "coachee", "coach",
    ]
    for t in tables:
        op.drop_table(t)
