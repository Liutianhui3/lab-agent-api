from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Enum, SmallInteger, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import TimestampMixin


if TYPE_CHECKING:
    from models.reservation import Reservation


class User(TimestampMixin, Base):
    """用户数据库模型；定义结构不会自动在数据库中建表。"""

    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint("status IN (0, 1)", name="ck_users_status"),
        {"comment": "用户信息表"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4, comment="用户 ID"
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, comment="用户名")
    password: Mapped[str] = mapped_column(String(255), comment="密码哈希，禁止存储明文")
    name: Mapped[str] = mapped_column(String(100), comment="姓名")
    role: Mapped[str] = mapped_column(
        Enum("student", "admin", name="user_role", validate_strings=True),
        default="student",
        server_default="student",
        comment="角色：student-学生，admin-管理员",
    )
    email: Mapped[str | None] = mapped_column(String(254), unique=True, comment="邮箱")
    phone: Mapped[str | None] = mapped_column(String(32), comment="手机号")
    avatar: Mapped[str | None] = mapped_column(String(2048), comment="头像 URL")
    status: Mapped[int] = mapped_column(
        SmallInteger,
        default=1,
        server_default="1",
        comment="状态：0-禁用，1-正常",
    )

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="user")
