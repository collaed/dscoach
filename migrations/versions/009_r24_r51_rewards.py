"""R24 + R51: reward catalog, redemption, and R49-score-as-currency integration.

Revision ID: 009
Revises: 008
Create Date: 2026-10-19

Adds reward_catalog (coach-defined, point-priced rewards) and
reward_redemption (a coachee's request against it, coach-approved).
Approval appends a negative score_log row (reason='reward_redeemed') -
the running R49 score IS the balance, no separate counter. Built as one
feature since R51 (spend the R49 score as currency, balance-checked,
no debt) is how redemption works from the start - there is no earlier
R24 balance representation to migrate away from.
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reward_catalog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("point_cost", sa.SmallInteger(), nullable=False),
        sa.Column("active", sa.SmallInteger(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "reward_redemption",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coachee_id", sa.Integer(), sa.ForeignKey("coachee.id"), nullable=False),
        sa.Column("reward_catalog_id", sa.Integer(), sa.ForeignKey("reward_catalog.id"), nullable=False),
        sa.Column("point_cost", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("requested_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by_coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("reward_redemption")
    op.drop_table("reward_catalog")
