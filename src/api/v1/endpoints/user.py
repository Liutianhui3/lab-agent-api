from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentAdmin, CurrentUser
from core.database import get_db
from schemas.auth import PasswordUpdateRequest
from schemas.response import BaseResponse
from schemas.user import (
    UserCreateRequest,
    UserPageResponse,
    UserProfileUpdateRequest,
    UserResponse,
    UserUpdateRequest,
)
from services import user_service

router = APIRouter(prefix="/user", tags=["用户管理"])


@router.get("/page", response_model=UserPageResponse[UserResponse])
async def get_user_page(
    _current_admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=100, description="每页条数"),
    role: Literal["admin", "student"] | None = Query(
        default=None, description="角色：admin-管理员，student-学生；不传查询全部"
    ),
    keyword: str | None = Query(
        default=None, max_length=254, description="搜索账号、姓名、邮箱或手机号"
    ),
) -> UserPageResponse[UserResponse]:
    """管理员分页查询用户，支持角色筛选及账号、姓名、邮箱或手机号模糊搜索。"""
    data = await user_service.get_user_page(
        db, page=page, size=size, keyword=keyword, role=role
    )
    return UserPageResponse[UserResponse](code=200, message="success", data=data)


@router.get("/info", response_model=BaseResponse[UserResponse])
def get_user_info(
    current_user: CurrentUser,
) -> BaseResponse[UserResponse]:
    """查询当前登录用户资料，不接受客户端指定其他用户 ID。"""
    # 路由仅接收请求并包装响应，用户资料处理交给 service。
    data = user_service.get_user_info(current_user)
    return BaseResponse[UserResponse].success(data=data)


@router.post("/update", response_model=BaseResponse[UserResponse])
async def update_user(
    request: UserProfileUpdateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[UserResponse]:
    """修改当前登录用户资料；用户身份从 Token 获取，不接受客户端指定 ID。"""
    data = await user_service.update_user(db, current_user, request)
    return BaseResponse[UserResponse].success(data=data, message="修改成功")


@router.post("/password", response_model=BaseResponse[None])
async def update_password(
    request: PasswordUpdateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[None]:
    """修改当前登录用户密码；身份由 Token 确定，旧密码由 service 验证。"""
    await user_service.update_password(db, current_user, request)
    return BaseResponse[None].success(message="密码修改成功")


@router.post("/create", response_model=BaseResponse[UserResponse])
async def create_user(
    request: UserCreateRequest,
    _current_admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[UserResponse]:
    """管理员新增用户，必须提供符合密码规则的密码。"""
    return BaseResponse[UserResponse].success(
        data=await user_service.create_user(db, request), message="新增成功"
    )


@router.put("/{user_id}", response_model=BaseResponse[UserResponse])
async def update_managed_user(
    user_id: UUID,
    request: UserUpdateRequest,
    _current_admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[UserResponse]:
    """管理员更新指定用户。"""
    return BaseResponse[UserResponse].success(
        data=await user_service.update_managed_user(db, user_id, request), message="修改成功"
    )


@router.delete("/{user_id}", response_model=BaseResponse[None])
async def delete_user(
    user_id: UUID,
    _current_admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[None]:
    """管理员删除已禁用的用户。"""
    await user_service.delete_user(db, user_id)
    return BaseResponse[None].success(message="删除成功")
