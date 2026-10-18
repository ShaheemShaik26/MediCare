"""Create the initial schema and add session token versioning.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("auth_token_version", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_users_id", "users", ["id"], unique=False)
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    elif "auth_token_version" not in {
        column["name"] for column in inspect(bind).get_columns("users")
    }:
        op.add_column(
            "users",
            sa.Column("auth_token_version", sa.Integer(), server_default="0", nullable=False),
        )

    if "documents" not in tables:
        op.create_table(
            "documents",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=128), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("preview_text", sa.Text(), nullable=True),
            sa.Column("document_type", sa.String(length=128), nullable=True),
            sa.Column("document_date", sa.String(length=32), nullable=True),
            sa.Column("provider_name", sa.String(length=255), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_documents_id", "documents", ["id"], unique=False)
        op.create_index("ix_documents_owner_id", "documents", ["owner_id"], unique=False)

    if "medical_facts" not in tables:
        op.create_table(
            "medical_facts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("fact_type", sa.String(length=64), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("source_excerpt", sa.Text(), nullable=True),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_medical_facts_id", "medical_facts", ["id"], unique=False)
        op.create_index("ix_medical_facts_owner_id", "medical_facts", ["owner_id"], unique=False)
        op.create_index("ix_medical_facts_document_id", "medical_facts", ["document_id"], unique=False)


def downgrade() -> None:
    raise RuntimeError(
        "The initial baseline is intentionally non-destructive and cannot be downgraded. "
        "Create a forward migration for schema changes."
    )
