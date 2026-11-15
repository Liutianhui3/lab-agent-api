import re
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic.alias_generators import to_camel


class UserUpdateRequest(BaseModel):
    """修改当前用户资料：未传字段不更新，可空字段传 null 表示清空。"""

    # 不接受 role、status、password 等字段，避免通过资料修改接口变更权限。
    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
    ] = Field(default=None, description="用户名；可不传，但不能为 null 或空白")

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("用户名不能为 null")
        return value

    name: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ] = Field(default=None, description="姓名；可不传，但不能为 null 或空白")
    email: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=254),
    ] = Field(default=None, description="邮箱；null 表示清空，唯一性由数据库保证")
    phone: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=32),
    ] = Field(default=None, description="手机号；null 表示清空")
    avatar: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2048),
    ] = Field(default=None, description="头像 URL 或上传接口返回的路径；null 表示清空")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        """姓名列不允许 NULL；未传字段不会触发此校验。"""
        if value is None:
            raise ValueError("姓名不能为 null")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("请输入有效的电子邮箱")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"\+?[\d\s()-]{6,32}", value):
            raise ValueError("请输入有效的手机号")
        return value

    @field_validator("avatar")
    @classmethod
    def validate_avatar(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlsplit(value)
        if (
            value.startswith("/uploads/")
            and not parsed.netloc
            and ".." not in parsed.path
        ):
            return value
        if parsed.scheme in {"https", "http"} and parsed.netloc:
            return value
        raise ValueError("头像地址必须是上传路径或 HTTP(S) URL")


class UserResponse(BaseModel):
    """用户响应数据，不包含密码或密码哈希。"""

    model_config = ConfigDict(
        from_attributes=True, alias_generator=to_camel, populate_by_name=True
    )

    id: UUID
    username: str
    name: str
    role: Literal["student", "admin"] = Field(description="student-学生，admin-管理员")
    email: str | None
    phone: str | None
    avatar: str | None
    status: Literal[0, 1] = Field(description="0-禁用，1-正常")
    created_at: datetime
    updated_at: datetime
