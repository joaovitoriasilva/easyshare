"""widen package_files.size to BigInteger

Revision ID: d4f6b8a0c2e3
Revises: c3e5a7b9d1f2
Create Date: 2026-07-16 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f6b8a0c2e3'
down_revision: str | None = 'c3e5a7b9d1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # INTEGER is 4 bytes on PostgreSQL (max ~2.1 GB); widen to BIGINT so a large
    # configured max_file_size cannot overflow the stored file size. A no-op on
    # SQLite, which stores integers dynamically, but kept for schema parity.
    with op.batch_alter_table('package_files', schema=None) as batch_op:
        batch_op.alter_column(
            'size',
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('package_files', schema=None) as batch_op:
        batch_op.alter_column(
            'size',
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
