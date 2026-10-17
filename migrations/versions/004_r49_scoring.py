"""R49: points & persisted daily score.

Revision ID: 004
Revises: 003
Create Date: 2026-10-17

Adds task_template.points (signed, default 0) and the append-only score_log
table. Uses batch_alter_table for the column add, matching 002/003, so
SQLite (tests) and PostgreSQL (prod) behave the same way.
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task_template") as batch_op:
        batch_op.add_column(sa.Column("points", sa.SmallInteger(), server_default="0", nullable=True))

    op.create_table(
        "score_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("points", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("task_assignment_id", sa.Integer(), sa.ForeignKey("task_assignment.id"), nullable=True),
        sa.Column("score_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("task_assignment_id", "reason"),
    )
    op.create_index("ix_score_log_coachee_date", "score_log", ["coachee_id", "score_date"])


def downgrade() -> None:
    op.drop_index("ix_score_log_coachee_date", table_name="score_log")
    op.drop_table("score_log")
    with op.batch_alter_table("task_template") as batch_op:
        batch_op.drop_column("points")
