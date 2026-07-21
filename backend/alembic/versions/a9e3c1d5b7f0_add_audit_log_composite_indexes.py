"""add audit log composite indexes

Revision ID: a9e3c1d5b7f0
Revises: b9d2f4a6c8e0
Create Date: 2026-07-21 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'a9e3c1d5b7f0'
down_revision: str | None = 'b9d2f4a6c8e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A composite (package_id, action) index for the owner-activity and
    # per-package stats queries, which always filter those two columns together,
    # and an actor index for the admin audit view's previously-unindexed
    # "filter by actor" path. These complement the existing single-column
    # indexes rather than replacing them.
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index(
            'ix_audit_log_package_action', ['package_id', 'action'], unique=False
        )
        batch_op.create_index('ix_audit_log_actor', ['actor'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_log_actor')
        batch_op.drop_index('ix_audit_log_package_action')
