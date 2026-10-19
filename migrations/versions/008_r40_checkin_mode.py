"""R40: check-in modes (optional/rewarded/required).

Revision ID: 008
Revises: 007
Create Date: 2026-10-19

Adds coachee.checkin_mode ('optional' | 'rewarded' | 'required', default
'optional'). Bonus/penalty amounts are configurable via the existing
coach.features JSON column (checkin_bonus, checkin_miss_penalty keys) -
same storage pattern as proof_bonus/week_start, no new columns needed for
those. See devdocs/roadmap.md R40.
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("coachee") as batch_op:
        batch_op.add_column(sa.Column("checkin_mode", sa.String(20), server_default="optional", nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("coachee") as batch_op:
        batch_op.drop_column("checkin_mode")
