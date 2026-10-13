"""encrypt totp secrets

Revision ID: 646a8075b1e6
Revises: 53c790ab1c3e
Create Date: 2026-10-10 15:43:46.507190

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

from src.modules.security.secret_box import open_secret, seal_secret

revision: str = "646a8075b1e6"
down_revision: str | Sequence[str] | None = "53c790ab1c3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rewrite(convert) -> None:
    # A --sql script cannot read rows; CD runs migrations online, where every secret is rewritten.
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT user_id, totp_secret FROM user_security WHERE totp_secret IS NOT NULL")).all()
    for user_id, secret in rows:
        bind.execute(
            sa.text("UPDATE user_security SET totp_secret = :secret WHERE user_id = :id"),
            {"secret": convert(secret), "id": user_id},
        )


def upgrade() -> None:
    op.alter_column("user_security", "totp_secret", type_=sa.String(255), existing_nullable=True)
    _rewrite(seal_secret)


def downgrade() -> None:
    _rewrite(open_secret)
    op.alter_column("user_security", "totp_secret", type_=sa.String(64), existing_nullable=True)
