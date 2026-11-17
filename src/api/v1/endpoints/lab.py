from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_current_admin, get_current_user
from core.database import get_db
from models.user import User
from schemas.lab import (
    LabCreateRequest,
    LabPageResponse,
    LabResponse,
    LabUpdateRequest,
)
from schemas.response import BaseResponse
from services import lab_service

router = APIRouter(prefix="/lab", tags=["实验室管理"])


@router.get("/page", response_model=LabPageResponse[LabResponse])
def get_lab_page(
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=100, description="每页条数"),
    status: int | None = Query(
        default=None, ge=0, le=1, description="状态：0-关闭，1-开放"
    ),
    keyword: str | None = Query(
        default=None, max_length=255, description="搜索实验室名称、编号或位置"
    ),
) -> LabPageResponse[LabResponse]:
    """登录用户分页查询实验室及全局统计。"""
    data = lab_service.get_lab_page(
        db, page=page, size=size, keyword=keyword, status=status
    )
    return LabPageResponse[LabResponse](code=200, message="success", data=data)


@router.get("/info", response_model=BaseResponse[LabResponse])
def get_lab_info(
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    lab_code: str = Query(min_length=1, max_length=50, description="实验室业务编号"),
) -> BaseResponse[LabResponse]:
    """登录用户按 lab_code 精确查询实验室详情。"""
    return BaseResponse[LabResponse].success(
        data=lab_service.get_lab_by_code(db, lab_code)
    )


@router.post("/create", response_model=BaseResponse[LabResponse])
def create_lab(
    request: LabCreateRequest,
    _current_admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> BaseResponse[LabResponse]:
    """管理员新增实验室。"""
    return BaseResponse[LabResponse].success(
        data=lab_service.create_lab(db, request), message="新增成功"
    )


@router.put("/{lab_id}", response_model=BaseResponse[LabResponse])
def update_lab(
    lab_id: int,
    request: LabUpdateRequest,
    _current_admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> BaseResponse[LabResponse]:
    """管理员更新指定实验室。"""
    return BaseResponse[LabResponse].success(
        data=lab_service.update_lab(db, lab_id, request), message="修改成功"
    )


@router.delete("/{lab_id}", response_model=BaseResponse[None])
def delete_lab(
    lab_id: int,
    _current_admin: Annotated[User, Depends(get_current_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> BaseResponse[None]:
    """管理员删除已关闭的实验室。"""
    lab_service.delete_lab(db, lab_id)
    return BaseResponse[None].success(message="删除成功")
