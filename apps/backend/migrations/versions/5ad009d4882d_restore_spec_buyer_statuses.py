"""restore spec buyer statuses

Revision ID: 5ad009d4882d
Revises: df644f9c15bf
Create Date: 2026-10-10 18:58:58.102076

"""

from collections.abc import Sequence

from alembic import op

revision: str = "5ad009d4882d"
down_revision: str | Sequence[str] | None = "df644f9c15bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE deal_buyers SET status = 'data_room_access' WHERE status = 'management_meeting'")
    op.execute("UPDATE deal_buyers SET status = 'client_approved' WHERE status = 'long_list' AND approval = 'approved'")


def downgrade() -> None:
    op.execute("UPDATE deal_buyers SET status = 'long_list' WHERE status = 'client_approved'")
    op.execute("UPDATE deal_buyers SET status = 'management_meeting' WHERE status = 'data_room_access'")
    op.execute("UPDATE deal_buyers SET status = 'binding_offer' WHERE status = 'preferred_bidder'")
