"""add upload_sessions for resumable chunked uploads

Revision ID: b9d2f4a6c8e0
Revises: a1c3e5f7b9d2
Create Date: 2026-07-20 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9d2f4a6c8e0"
down_revision: str | None = "a1c3e5f7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=255),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column("total_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "received", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("scratch_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["package_id"], ["packages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
        sa.UniqueConstraint("scratch_key"),
    )
    op.create_index(
        op.f("ix_upload_sessions_token"),
        "upload_sessions",
        ["token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_upload_sessions_package_id"),
        "upload_sessions",
        ["package_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_upload_sessions_package_id"), table_name="upload_sessions"
    )
    op.drop_index(
        op.f("ix_upload_sessions_token"), table_name="upload_sessions"
    )
    op.drop_table("upload_sessions")
