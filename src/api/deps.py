from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import decode_access_token
from models.user import User
from services.auth_service import is_token_revoked

# 1. 实例化 OAuth2PasswordBearer
# tokenUrl 应该指向你的登录接口路径，主要用于 Swagger UI 的 "Authorize" 按钮联调
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """
    公共依赖项：获取当前登录用户
    1. 自动从请求头 Authorization: Bearer <token> 中提取 Token
    2. 调用 security.py 解码 Token
    3. 查询数据库验证用户有效性、是否存在、是否被禁用
    4. 返回当前用户的 ORM 对象；身份无效抛出 401，用户禁用抛出 403
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )

    invalid_credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的登录凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 2. 解码 JWT Token
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    # JWT 签名有效也可能已经登出；所有受保护接口都必须检查撤销记录。
    if is_token_revoked(payload["jti"]):
        raise credentials_exception

    # 3. 提取并验证 UUID 用户 ID
    user_id: str | None = payload.get("sub")
    if not isinstance(user_id, str):
        raise invalid_credentials_exception
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise invalid_credentials_exception from None

    # 4. 去数据库查询用户真实状态（防止用户被删除或禁用后，旧 Token 仍然能用）
    user = db.get(User, user_uuid)
    if user is None:
        raise invalid_credentials_exception

    # 5. 仅允许 status=1 的正常用户访问；status=0 表示禁用
    if user.status != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    # 返回用户对象，后续在路由中可以直接使用
    return user
