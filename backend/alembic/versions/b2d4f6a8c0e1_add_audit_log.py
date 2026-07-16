"""add audit_log

Revision ID: b2d4f6a8c0e1
Revises: 1b6f0310842f
Create Date: 2026-07-16 14:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d4f6a8c0e1'
down_revision: str | None = '1b6f0310842f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('actor', sa.String(length=320), nullable=True),
        sa.Column('target', sa.String(length=255), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('client_ip', sa.String(length=64), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_audit_log_created_at'), ['created_at'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_audit_log_action'), ['action'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_action'))
        batch_op.drop_index(batch_op.f('ix_audit_log_created_at'))
    op.drop_table('audit_log')
