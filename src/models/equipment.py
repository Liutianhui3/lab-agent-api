from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:
    from models.lab import Lab
    from models.reservation import Reservation


class Equipment(TimestampMixin, Base):
    """实验室设备信息。"""

    __tablename__ = "equipments"
    __table_args__ = (
        CheckConstraint("status IN (0, 1)", name="ck_equipments_status"),
        {"comment": "实验室设备表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="设备 ID",
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, comment="设备编号")
    name: Mapped[str] = mapped_column(String(100), comment="设备名称")
    lab_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("labs.id", name="fk_equipments_lab_id"),
        index=True,
        comment="所属实验室 ID",
    )
    lab: Mapped["Lab"] = relationship("Lab")
    description: Mapped[str | None] = mapped_column(Text, comment="说明")
    img: Mapped[str | None] = mapped_column(String(2048), comment="图片")
    sepc: Mapped[str | None] = mapped_column(String(255), comment="型号规格")
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", comment="数量"
    )
    status: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1", comment="状态：0-维修，1-正常"
    )

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="equipment")
