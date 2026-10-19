"""R42: protocol mode toggle (formal/relaxed).

Revision ID: 006
Revises: 005
Create Date: 2026-10-19

Adds coachee.protocol_mode ('relaxed' | 'formal'), note.tagged_mode (the
coachee's protocol_mode at note-submission time, nullable), and the
append-only protocol_mode_log table for coach review of mode history.
See devdocs/roadmap.md R42.
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("coachee") as batch_op:
        batch_op.add_column(sa.Column("protocol_mode", sa.String(20), server_default="relaxed", nullable=True))
    with op.batch_alter_table("note") as batch_op:
        batch_op.add_column(sa.Column("tagged_mode", sa.String(20), nullable=True))

    op.create_table(
        "protocol_mode_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("changed_by_coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("protocol_mode_log")
    with op.batch_alter_table("note") as batch_op:
        batch_op.drop_column("tagged_mode")
    with op.batch_alter_table("coachee") as batch_op:
        batch_op.drop_column("protocol_mode")
