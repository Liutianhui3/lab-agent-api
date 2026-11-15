from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
from core.database import get_db
from models.user import User
from schemas.auth import PasswordUpdateRequest
from schemas.response import BaseResponse
from schemas.user import UserResponse, UserUpdateRequest
from services import user_service

router = APIRouter(prefix="/user", tags=["用户管理"])


@router.get("/info", response_model=BaseResponse[UserResponse])
def get_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> BaseResponse[UserResponse]:
    """查询当前登录用户资料，不接受客户端指定其他用户 ID。"""
    # 路由仅接收请求并包装响应，用户资料处理交给 service。
    data = user_service.get_user_info(current_user)
    return BaseResponse[UserResponse].success(data=data)


@router.post("/update", response_model=BaseResponse[UserResponse])
def update_user(
    request: UserUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BaseResponse[UserResponse]:
    """修改当前登录用户资料；用户身份从 Token 获取，不接受客户端指定 ID。"""
    data = user_service.update_user(db, current_user, request)
    return BaseResponse[UserResponse].success(data=data, message="修改成功")


@router.post("/password", response_model=BaseResponse[None])
def update_password(
    request: PasswordUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BaseResponse[None]:
    """修改当前登录用户密码；身份由 Token 确定，旧密码由 service 验证。"""
    user_service.update_password(db, current_user, request)
    return BaseResponse[None].success(message="密码修改成功")
