from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentAdmin, CurrentUser
from core.database import get_db
from models.user import User
from schemas.equipment import (
    EquipmentCreateRequest,
    EquipmentPageResponse,
    EquipmentResponse,
    EquipmentUpdateRequest,
)
from schemas.response import BaseResponse
from services import equipment_service

router = APIRouter(prefix="/equipment", tags=["设备管理"])


@router.get("/page", response_model=EquipmentPageResponse[EquipmentResponse])
async def get_equipment_page(
    _current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=100, description="每页条数"),
    lab_id: int | None = Query(default=None, gt=0, description="所属实验室 ID"),
    status: int | None = Query(default=None, ge=0, le=1, description="状态：0-维修，1-正常"),
    keyword: str | None = Query(default=None, max_length=255, description="搜索设备名称或编号"),
) -> EquipmentPageResponse[EquipmentResponse]:
    """登录用户分页查询设备。"""
    data = await equipment_service.get_equipment_page(
        db, page=page, size=size, keyword=keyword, lab_id=lab_id, status=status
    )
    return EquipmentPageResponse[EquipmentResponse](code=200, message="success", data=data)


@router.post("/create", response_model=BaseResponse[EquipmentResponse])
async def create_equipment(
    request: EquipmentCreateRequest,
    _current_admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[EquipmentResponse]:
    """管理员新增设备。"""
    return BaseResponse[EquipmentResponse].success(
        data=await equipment_service.create_equipment(db, request), message="新增成功"
    )


@router.put("/{equipment_id}", response_model=BaseResponse[EquipmentResponse])
async def update_equipment(
    equipment_id: int,
    request: EquipmentUpdateRequest,
    _current_admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[EquipmentResponse]:
    """管理员编辑指定设备。"""
    return BaseResponse[EquipmentResponse].success(
        data=await equipment_service.update_equipment(db, equipment_id, request), message="修改成功"
    )


@router.delete("/{equipment_id}", response_model=BaseResponse[None])
async def delete_equipment(
    equipment_id: int,
    _current_admin: CurrentAdmin,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[None]:
    """管理员删除指定设备。"""
    await equipment_service.delete_equipment(db, equipment_id)
    return BaseResponse[None].success(message="删除成功")
