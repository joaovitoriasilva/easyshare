"""add share expiry, view counter and share access codes

Revision ID: f8c2a3b5d7e9
Revises: e7b1c4d9f2a3
Create Date: 2026-07-19 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f8c2a3b5d7e9'
down_revision: str | None = 'e7b1c4d9f2a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Optional share expiry (NULL = never) and a denormalised view counter that
    # replaces a per-view audit row. server_default backfills existing rows to 0.
    with op.batch_alter_table('shares', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                'view_count',
                sa.BigInteger(),
                nullable=False,
                server_default='0',
            )
        )

    # One-time verification codes for restricted shares (keyed hash only).
    op.create_table(
        'share_access_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('share_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['share_id'], ['shares.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('share_id', 'email', name='uq_share_code_email'),
    )
    with op.batch_alter_table('share_access_codes', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_share_access_codes_share_id'), ['share_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_share_access_codes_email'), ['email'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('share_access_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_share_access_codes_email'))
        batch_op.drop_index(batch_op.f('ix_share_access_codes_share_id'))
    op.drop_table('share_access_codes')

    with op.batch_alter_table('shares', schema=None) as batch_op:
        batch_op.drop_column('view_count')
        batch_op.drop_column('expires_at')
