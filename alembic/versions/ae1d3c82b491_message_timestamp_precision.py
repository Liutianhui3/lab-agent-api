"""Preserve message timestamp precision and support full-length messages."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "ae1d3c82b491"
down_revision = "d6b12f91bd5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "messages",
        "created_at",
        existing_type=mysql.DATETIME(),
        type_=mysql.DATETIME(fsp=6),
        existing_nullable=False,
        server_default=None,
        existing_comment="创建时间",
    )
    op.alter_column(
        "messages",
        "content",
        existing_type=mysql.TEXT(),
        type_=mysql.LONGTEXT(),
        existing_nullable=False,
        existing_comment="消息内容",
    )


def downgrade() -> None:
    op.alter_column(
        "messages",
        "content",
        existing_type=mysql.LONGTEXT(),
        type_=mysql.TEXT(),
        existing_nullable=False,
        existing_comment="消息内容",
    )
    op.alter_column(
        "messages",
        "created_at",
        existing_type=mysql.DATETIME(fsp=6),
        type_=mysql.DATETIME(),
        existing_nullable=False,
        server_default=sa.text("now()"),
        existing_comment="创建时间",
    )
