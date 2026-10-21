"""Add private self-reported lifestyle profile.

Revision ID: 0002_lifestyle
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_lifestyle"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lifestyle_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("activity_frequency", sa.String(length=32), nullable=True),
        sa.Column("diet_notes", sa.Text(), nullable=True),
        sa.Column("sleep_hours", sa.Float(), nullable=True),
        sa.Column("tobacco_use", sa.String(length=32), nullable=True),
        sa.Column("alcohol_frequency", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lifestyle_profiles_id", "lifestyle_profiles", ["id"], unique=False)
    op.create_index("ix_lifestyle_profiles_owner_id", "lifestyle_profiles", ["owner_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_lifestyle_profiles_owner_id", table_name="lifestyle_profiles")
    op.drop_index("ix_lifestyle_profiles_id", table_name="lifestyle_profiles")
    op.drop_table("lifestyle_profiles")
