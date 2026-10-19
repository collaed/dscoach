"""R47: unavailability protocol.

Revision ID: 007
Revises: 006
Create Date: 2026-10-19

Adds coachee.unavailable_since (DateTime, set when a declaration is active),
coachee.unavailable_until (Date, nullable - NULL means indefinite) and
coachee.unavailable_note (String(300)). No new table: "ending" an
unavailability just clears all three columns, and an expired
unavailable_until is detected by comparison rather than by a sweep.
See devdocs/roadmap.md R47.
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("coachee") as batch_op:
        batch_op.add_column(sa.Column("unavailable_since", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("unavailable_until", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("unavailable_note", sa.String(300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("coachee") as batch_op:
        batch_op.drop_column("unavailable_note")
        batch_op.drop_column("unavailable_until")
        batch_op.drop_column("unavailable_since")
