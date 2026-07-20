"""add users failed_login_attempts and locked_until

Revision ID: a1c3e5f7b9d2
Revises: f8c2a3b5d7e9
Create Date: 2026-07-20 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c3e5f7b9d2'
down_revision: str | None = 'f8c2a3b5d7e9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Account-lockout bookkeeping. ``failed_login_attempts`` backfills existing
    # rows to 0 via server_default; ``locked_until`` is nullable (NULL = not
    # locked). New rows get their values from the ORM defaults.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'failed_login_attempts',
                sa.Integer(),
                nullable=False,
                server_default='0',
            )
        )
        batch_op.add_column(
            sa.Column(
                'locked_until',
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_login_attempts')
