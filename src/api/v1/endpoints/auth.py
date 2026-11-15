from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import oauth2_scheme
from core.database import get_db
from schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from schemas.response import BaseResponse
from schemas.user import UserResponse
from services.auth_service import login_user, logout_user, register_user

router = APIRouter(prefix="/auth", tags=["权限验证"])

SessionDependency = Annotated[Session, Depends(get_db)]


@router.post("/register", response_model=BaseResponse[None])
def register(request: RegisterRequest, db: SessionDependency) -> UserResponse:
    # 逻辑写在sevice层
    register_user(db, request)
    return BaseResponse.success(message="注册成功")


@router.post("/login", response_model=BaseResponse[LoginResponse])
def login(request: LoginRequest, db: SessionDependency) -> BaseResponse[LoginResponse]:
    # 路由负责接收参数和包装响应；身份校验、状态检查和签发令牌由 service 完成。
    data = login_user(db, request)
    return BaseResponse[LoginResponse].success(data=data, message="登录成功")


@router.post("/logout", response_model=BaseResponse[None])
def logout(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> BaseResponse[None]:
    # 从 Authorization: Bearer <token> 提取令牌，撤销逻辑放在 service 层。
    logout_user(token)
    return BaseResponse[None].success(message="登出成功")
