"""add is_admin and audit_log.package_id

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-07-16 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e5a7b9d1f2'
down_revision: str | None = 'b2d4f6a8c0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_admin',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('package_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_audit_log_package_id'), ['package_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_package_id'))
        batch_op.drop_column('package_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_admin')
