"""Convert DateTime columns to TIMESTAMPTZ (PostgreSQL).

Revision ID: 002
Revises: 001
Create Date: 2026-08-23

All existing timestamp columns are converted to TIMESTAMP WITH TIME ZONE.
Existing naive timestamps are treated as UTC (which they were in practice).
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

# All tables with DateTime columns (from models.py analysis)
TABLES_WITH_TIMESTAMPS = {
    "coach": ["created_at"],
    "coachee": ["created_at"],
    "task_template": ["created_at"],
    "task_assignment": ["visible_after", "frozen_after", "responded_at", "created_at"],
    "checkin": ["created_at"],
    "acknowledgement": ["created_at"],
    "tracking_log": ["created_at"],
    "note": ["scheduled_at", "read_at", "created_at"],
    "mental_conditioning": ["created_at"],
    "mental_conditioning_response": ["created_at"],
    "psychological_profile": ["updated_at"],
    "contract_history": ["created_at"],
    "audit_log": ["created_at"],
    "weekly_summary": ["created_at"],
    "voice_note": ["created_at"],
    "goal": ["created_at"],
    "journal": ["created_at"],
    "progress_photo": ["created_at"],
    "support_message": ["created_at"],
    "badge": ["created_at"],
    "ritual": ["created_at"],
    "ritual_log": ["created_at"],
    "auto_rule": ["created_at"],
    "week_plan": ["created_at"],
    "onboarding_step": ["created_at"],
    "payment_plan": ["created_at"],
    "payment_log": ["confirmed_at", "created_at"],
    "creative_collection": ["created_at"],
    "creative_constraint": ["created_at"],
    "creative_work": ["created_at"],
}


def upgrade() -> None:
    """Alter all DateTime columns to TIMESTAMP WITH TIME ZONE."""
    conn = op.get_bind()
    # Get list of existing tables
    result = conn.execute(
        sa.text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    existing_tables = {row[0] for row in result}

    for table, columns in TABLES_WITH_TIMESTAMPS.items():
        if table not in existing_tables:
            continue  # Skip tables not yet created in this DB
        for col in columns:
            # Check if column exists
            col_check = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name=:table AND column_name=:col"
                ),
                {"table": table, "col": col},
            )
            if col_check.fetchone():
                op.execute(
                    sa.text(
                        f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMP WITH TIME ZONE "
                        f"USING {col} AT TIME ZONE 'UTC'"
                    )
                )


def downgrade() -> None:
    """Revert to TIMESTAMP WITHOUT TIME ZONE."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    )
    existing_tables = {row[0] for row in result}

    for table, columns in TABLES_WITH_TIMESTAMPS.items():
        if table not in existing_tables:
            continue
        for col in columns:
            col_check = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name=:table AND column_name=:col"
                ),
                {"table": table, "col": col},
            )
            if col_check.fetchone():
                op.execute(
                    sa.text(
                        f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMP WITHOUT TIME ZONE"
                    )
                )
