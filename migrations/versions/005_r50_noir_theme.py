"""R50: FetLife-inspired noir theme preference.

Revision ID: 005
Revises: 004
Create Date: 2026-10-17

Adds coach.theme_pref and coachee.theme_pref ('default' | 'noir'), mirroring
the existing font_pref column exactly. Pure CSS re-tokenization - no other
schema changes. See devdocs/plan-aesthetic-noir.md.
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("coach") as batch_op:
        batch_op.add_column(sa.Column("theme_pref", sa.String(20), server_default="default", nullable=True))
    with op.batch_alter_table("coachee") as batch_op:
        batch_op.add_column(sa.Column("theme_pref", sa.String(20), server_default="default", nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("coachee") as batch_op:
        batch_op.drop_column("theme_pref")
    with op.batch_alter_table("coach") as batch_op:
        batch_op.drop_column("theme_pref")
