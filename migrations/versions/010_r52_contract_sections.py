"""R52: contract section library + sample-task association.

Revision ID: 010
Revises: 009
Create Date: 2026-10-19

Adds contract_section (coach_id NULL = system default, shared/read-only/
cloneable; else private to that coach) and contract_section_task (sample
tasks offered - never forced, REQ-52.6 - when a section is included in a
drafted contract). No change to coachee.contract_text/contract_history
(REQ-52.5): sections are a scaffold for producing that same text, not a
new storage mechanism. See devdocs/plan-contract-drafting.md.
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_section",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coach.id"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(40), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("reusability", sa.String(20), server_default="custom"),
        sa.Column("sort_hint", sa.SmallInteger(), server_default="0"),
        sa.Column("active", sa.SmallInteger(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "contract_section_task",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("contract_section.id"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(20), server_default="mental"),
        sa.Column("difficulty", sa.String(20), server_default="medium"),
        sa.Column("recurrence", sa.String(20), server_default="once"),
        sa.Column("recur_days", sa.Integer(), nullable=True),
        sa.Column("is_reserve", sa.SmallInteger(), server_default="0"),
        sa.Column("proof_pct", sa.SmallInteger(), server_default="0"),
        sa.Column("points", sa.SmallInteger(), server_default="0"),
        sa.Column("tags", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("contract_section_task")
    op.drop_table("contract_section")
