from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
)
from pydantic.alias_generators import to_camel

from schemas.password import validate_password_rules
from schemas.user import UserResponse


class LoginRequest(BaseModel):
    """用户名密码登录参数；密码保留原始内容，不去除空格。"""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ] = Field(description="用户名")
    password: SecretStr = Field(min_length=1, description="登录密码")


class RegisterRequest(BaseModel):
    """新用户注册参数。"""

    model_config = ConfigDict(extra="forbid")

    username: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ] = Field(description="用户名")
    password: SecretStr = Field(
        description="8–20 位，须包含大写字母、小写字母和数字；符号可选，不允许空格或中文"
    )
    email: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)
    ] = Field(description="邮箱")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        return validate_password_rules(value)


class PasswordUpdateRequest(BaseModel):
    """修改当前用户密码，旧密码用于验证身份，新密码遵循注册密码规则。"""

    model_config = ConfigDict(extra="forbid")

    old_password: SecretStr = Field(min_length=1, description="当前密码")
    new_password: SecretStr = Field(description="新密码")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: SecretStr) -> SecretStr:
        return validate_password_rules(value)


class LoginResponse(BaseModel):
    """登录成功后返回的访问令牌和当前用户资料。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    access_token: str = Field(description="JWT 访问令牌")
    user: UserResponse
