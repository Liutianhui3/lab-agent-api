"""Add unique constraint to user email.

Revision ID: b6f12a7d9e03
Revises: 70c75ec930a4
"""

from alembic import op

revision = "b6f12a7d9e03"
down_revision = "70c75ec930a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
