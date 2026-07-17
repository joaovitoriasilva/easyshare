"""add user storage_quota and package_files.download_count

Revision ID: e7b1c4d9f2a3
Revises: d4f6b8a0c2e3
Create Date: 2026-07-17 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from app.core.config import settings


revision: str = 'e7b1c4d9f2a3'
down_revision: str | None = 'd4f6b8a0c2e3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Per-user storage budget (bytes; 0 = unlimited). Added nullable first so
    # existing rows can be backfilled to the configured default before the
    # NOT NULL constraint is applied.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('storage_quota', sa.BigInteger(), nullable=True)
        )
    op.execute(
        sa.text('UPDATE users SET storage_quota = :quota').bindparams(
            quota=settings.storage_quota_per_user
        )
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'storage_quota', existing_type=sa.BigInteger(), nullable=False
        )

    # Denormalised per-file download counter. server_default backfills existing
    # rows to 0; new rows get their value from the ORM default.
    with op.batch_alter_table('package_files', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'download_count',
                sa.BigInteger(),
                nullable=False,
                server_default='0',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('package_files', schema=None) as batch_op:
        batch_op.drop_column('download_count')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('storage_quota')
