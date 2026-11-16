from datetime import datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic.alias_generators import to_camel

from schemas.response import BaseResponse, PageData


class LabResponse(BaseModel):
    """实验室响应，支持从 ORM 对象读取字段。"""

    model_config = ConfigDict(
        from_attributes=True, alias_generator=to_camel, populate_by_name=True
    )

    id: int
    lab_code: str
    name: str
    location: str | None
    capacity: int
    description: str | None
    img: str | None
    open_time: time | None
    close_time: time | None
    status: Literal[0, 1] = Field(description="0-关闭，1-开放")
    created_at: datetime
    updated_at: datetime


class LabCreateRequest(BaseModel):
    """新增实验室参数；主键和时间戳由服务端生成。"""

    model_config = ConfigDict(extra="forbid")

    lab_code: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ] = Field(description="实验室业务编号")
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] = Field(description="名称")
    location: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=255)
    ] = Field(default=None, description="位置")
    capacity: int = Field(default=0, ge=0, le=2147483647, description="容量")
    description: str | None = Field(default=None, description="描述")
    img: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
    ] = Field(default=None, description="封面图片")
    open_time: time | None = Field(default=None, description="开放开始时间")
    close_time: time | None = Field(default=None, description="开放结束时间")
    status: Literal[0, 1] = Field(default=1, description="0-关闭，1-开放")


class LabUpdateRequest(BaseModel):
    """部分更新实验室；未传字段不更新，可空字段传 null 表示清空。"""

    model_config = ConfigDict(extra="forbid")

    lab_code: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
    ] = Field(default=None, description="业务编号；可不传，不能为 null 或空白")
    name: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ] = Field(default=None, description="名称；可不传，不能为 null 或空白")
    location: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=255)
    ] = Field(default=None, description="位置；null 表示清空")
    capacity: int | None = Field(
        default=None, ge=0, le=2147483647, description="容量；可不传，不能为 null"
    )
    description: str | None = Field(default=None, description="描述；null 表示清空")
    img: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
    ] = Field(default=None, description="封面图片；null 表示清空")
    open_time: time | None = Field(
        default=None, description="开放开始时间；null 表示清空"
    )
    close_time: time | None = Field(
        default=None, description="开放结束时间；null 表示清空"
    )
    status: Literal[0, 1] | None = Field(
        default=None, description="0-关闭，1-开放；可不传，不能为 null"
    )

    @field_validator("lab_code", "name", "capacity", "status")
    @classmethod
    def validate_non_nullable_fields(cls, value):
        if value is None:
            raise ValueError("编号、名称、容量和状态不能为 null")
        return value


class LabPageData[T](PageData[T]):
    """实验室分页数据及不受筛选条件影响的全局统计。"""

    global_total: int = Field(default=0, description="实验室总数")
    open_count: int = Field(default=0, description="开放中的实验室数")
    closed_count: int = Field(default=0, description="已关闭的实验室数")
    total_capacity: int = Field(default=0, description="所有实验室总容量")


class LabPageResponse[T](BaseResponse[LabPageData[T]]):
    """实验室分页 API 响应。"""
