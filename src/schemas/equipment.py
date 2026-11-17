from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic.alias_generators import to_camel

from schemas.response import BaseResponse, PageData


class EquipmentResponse(BaseModel):
    """设备响应，支持从 ORM 对象读取字段。"""

    model_config = ConfigDict(
        from_attributes=True, alias_generator=to_camel, populate_by_name=True
    )

    id: int
    code: str
    name: str
    lab_id: int
    description: str | None
    img: str | None
    sepc: str | None
    quantity: int
    status: Literal[0, 1] = Field(description="0-维修，1-正常")
    created_at: datetime
    updated_at: datetime


class EquipmentCreateRequest(BaseModel):
    """新增设备参数；主键和时间戳由服务端生成。"""

    model_config = ConfigDict(extra="forbid")

    code: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ] = Field(description="设备编号")
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] = Field(description="设备名称")
    lab_id: int = Field(description="所属实验室 ID", gt=0)
    description: str | None = Field(default=None, description="说明")
    img: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
    ] = Field(default=None, description="图片")
    sepc: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ] = Field(default=None, description="型号规格")
    quantity: int = Field(default=1, ge=1, le=2147483647, description="数量")
    status: Literal[0, 1] = Field(default=1, description="0-维修，1-正常")


class EquipmentUpdateRequest(BaseModel):
    """部分更新设备；未传字段不更新，可空字段传 null 表示清空。"""

    model_config = ConfigDict(extra="forbid")

    code: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
    ] = Field(default=None, description="设备编号；可不传，不能为 null 或空白")
    name: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ] = Field(default=None, description="设备名称；可不传，不能为 null 或空白")
    lab_id: int | None = Field(default=None, gt=0, description="所属实验室 ID")
    description: str | None = Field(default=None, description="说明；null 表示清空")
    img: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
    ] = Field(default=None, description="图片；null 表示清空")
    sepc: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ] = Field(default=None, description="型号规格；null 表示清空")
    quantity: int | None = Field(default=None, ge=1, le=2147483647, description="数量")
    status: Literal[0, 1] | None = Field(default=None, description="0-维修，1-正常")

    @field_validator("code", "name", "lab_id", "quantity", "status")
    @classmethod
    def validate_non_nullable_fields(cls, value):
        if value is None:
            raise ValueError("设备编号、名称、所属实验室、数量和状态不能为 null")
        return value


class EquipmentPageData[T](PageData[T]):
    """设备分页数据及不受筛选条件影响的全局统计。"""

    global_total: int = Field(default=0, description="设备总数")
    normal_count: int = Field(default=0, description="正常设备数")
    maintenance_count: int = Field(default=0, description="维修设备数")
    total_quantity: int = Field(default=0, description="设备总数量")


class EquipmentPageResponse[T](BaseResponse[EquipmentPageData[T]]):
    """设备分页 API 响应。"""
