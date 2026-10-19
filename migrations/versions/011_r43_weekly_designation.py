"""R43: weekly status designation (GREEN/YELLOW/RED).

Revision ID: 011
Revises: 010
Create Date: 2026-10-19

Adds weekly_summary.designation ('green' | 'yellow' | 'red', nullable -
not every week gets one). Coach-assigned via a new
/coach/coachee/<cid>/weekly-designation route, found-or-created against
the same Monday-aligned week_start the existing weekly summary stats use.
See devdocs/roadmap.md R43.
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("weekly_summary") as batch_op:
        batch_op.add_column(sa.Column("designation", sa.String(10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("weekly_summary") as batch_op:
        batch_op.drop_column("designation")
