"""R48: probabilistic proof demand.

Revision ID: 003
Revises: 002
Create Date: 2026-10-17

Adds task_template.proof_pct (0-100 chance a given occurrence demands a
photo, default 0 = current behaviour unchanged) and
task_assignment.proof_required (the once-at-creation roll result,
persisted so it's stable across reloads - see tasks.py::_roll_proof_required).

Uses batch_alter_table so this also applies cleanly on SQLite (tests),
not just PostgreSQL (prod).
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("task_template") as batch_op:
        batch_op.add_column(sa.Column("proof_pct", sa.SmallInteger(), server_default="0", nullable=True))
    with op.batch_alter_table("task_assignment") as batch_op:
        batch_op.add_column(sa.Column("proof_required", sa.SmallInteger(), server_default="0", nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("task_assignment") as batch_op:
        batch_op.drop_column("proof_required")
    with op.batch_alter_table("task_template") as batch_op:
        batch_op.drop_column("proof_pct")
