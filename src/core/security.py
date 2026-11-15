from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from passlib.context import CryptContext

from core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与数据库中的哈希密码是否一致"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """对用户输入的明文密码进行 bcrypt 哈希加密"""
    return pwd_context.hash(password)


def create_access_token(
    subject: str | Any, expires_delta: timedelta | None = None
) -> str:
    """生成 JWT Access Token

    :param subject: 载荷中携带的唯一标识（通常是用户名或用户 ID，放入 sub 字段）
    :param expires_delta: 自定义过期时间间隔
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    # 构造 Payload
    to_encode = {
        "exp": expire,  # 过期时间
        "sub": str(subject),  # 主题/用户标识
        "iat": datetime.now(UTC),  # 签发时间
        "jti": str(uuid4()),  # 每次登录生成不同令牌，避免同一秒登录共享 Token。
    }

    # 签发 Token
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict | None:
    """解码并验证 JWT Token

    :return: 验证成功返回 payload 字典，失败（过期或篡改）返回 None
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            options={"require": ["sub", "jti", "iat", "exp"]},
        )
        if not isinstance(payload["jti"], str) or not payload["jti"]:
            return None
        if not isinstance(payload["exp"], int):
            return None
        return payload
    except jwt.PyJWTError:
        # 捕获 Token 过期、签名错误、格式错误等所有 PyJWT 异常
        return None
