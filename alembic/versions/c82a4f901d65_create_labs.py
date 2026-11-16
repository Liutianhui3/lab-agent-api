"""Create labs table.

Revision ID: c82a4f901d65
Revises: b6f12a7d9e03
"""

from alembic import op
import sqlalchemy as sa


revision = "c82a4f901d65"
down_revision = "b6f12a7d9e03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "labs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="内部主键"),
        sa.Column("lab_code", sa.String(50), nullable=False, comment="实验室业务编号"),
        sa.Column("name", sa.String(100), nullable=False, comment="名称"),
        sa.Column("location", sa.String(255), nullable=True, comment="位置"),
        sa.Column("capacity", sa.Integer(), server_default="0", nullable=False, comment="容量"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("img", sa.String(2048), nullable=True, comment="封面图片"),
        sa.Column("open_time", sa.Time(), nullable=True, comment="开放开始时间"),
        sa.Column("close_time", sa.Time(), nullable=True, comment="开放结束时间"),
        sa.Column("status", sa.SmallInteger(), server_default="1", nullable=False, comment="状态：0-关闭，1-开放"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="更新时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lab_code", name="uq_labs_lab_code"),
        sa.CheckConstraint("status IN (0, 1)", name="ck_labs_status"),
        comment="实验室信息表",
    )


def downgrade() -> None:
    op.drop_table("labs")
