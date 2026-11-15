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

from schemas.user import UserResponse


def validate_password_rules(value: SecretStr) -> SecretStr:
    """校验注册及修改密码的统一规则，保留用户输入原样。"""
    password = value.get_secret_value()
    errors = []
    if not password:
        raise ValueError("请输入密码")
    if len(password) < 8:
        errors.append("密码至少需要 8 位")
    if len(password) > 20:
        errors.append("密码不能超过 20 位")
    if not any("A" <= char <= "Z" for char in password):
        errors.append("缺少大写字母")
    if not any("a" <= char <= "z" for char in password):
        errors.append("缺少小写字母")
    if not any("0" <= char <= "9" for char in password):
        errors.append("缺少数字")
    if any(char.isspace() or char == "\ufeff" for char in password):
        errors.append("密码不能包含空格或其他空白字符")
    if any(
        not "!" <= char <= "~" and not char.isspace() and char != "\ufeff"
        for char in password
    ):
        errors.append("密码只能包含英文字母、数字和英文符号，不能包含中文等字符")
    if errors:
        raise ValueError("；".join(errors))
    return value


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
