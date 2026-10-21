"""Add editable clinical event dates and measurement values.

Revision ID: 0003_reviewable_facts
Revises: 0002_lifestyle
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_reviewable_facts"
down_revision = "0002_lifestyle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("medical_facts", sa.Column("event_date", sa.Date(), nullable=True))
    op.add_column("medical_facts", sa.Column("numeric_value", sa.Float(), nullable=True))
    op.add_column("medical_facts", sa.Column("unit", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("medical_facts", "unit")
    op.drop_column("medical_facts", "numeric_value")
    op.drop_column("medical_facts", "event_date")
