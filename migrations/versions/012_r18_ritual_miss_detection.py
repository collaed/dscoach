"""R18: automatic ritual-miss detection.

Revision ID: 012
Revises: 011
Create Date: 2026-10-19

Adds ritual_log.status ('completed' | 'missed', default 'completed' so
every pre-existing row still reads as a completion). A miss is now a row
too, under the SAME (ritual_id, coachee_id, completed_date) unique
constraint that already existed - a given ritual on a given day is either
completed or missed, never both, and the constraint enforces that for
free. See devdocs/roadmap.md R18.
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ritual_log") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(10), server_default="completed", nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ritual_log") as batch_op:
        batch_op.drop_column("status")
