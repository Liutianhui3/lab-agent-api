from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentUser
from core.database import get_db
from schemas.reservation import (
    ReservationCreateRequest,
    ReservationPageResponse,
    ReservationResponse,
    ReservationStatusRequest,
)
from schemas.response import BaseResponse
from services import reservation_service

router = APIRouter(prefix="/reservation", tags=["预约管理"])


@router.get("/page", response_model=ReservationPageResponse[ReservationResponse])
async def get_reservation_page(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    status: int | None = Query(default=None, ge=0, le=3),
) -> ReservationPageResponse[ReservationResponse]:
    data = await reservation_service.get_reservation_page(
        db, current_user, page, size, status
    )
    return ReservationPageResponse[ReservationResponse](
        code=200, message="success", data=data
    )


@router.post("/create", response_model=BaseResponse[ReservationResponse])
async def create_reservation(
    request: ReservationCreateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[ReservationResponse]:
    """登录用户创建预约。"""
    reservation = await reservation_service.create_reservation(db, current_user, request)
    return BaseResponse[ReservationResponse].success(
        data=ReservationResponse.model_validate(reservation), message="预约成功，待审核"
    )


@router.patch(
    "/{reservation_id}/status", response_model=BaseResponse[ReservationResponse]
)
async def update_reservation_status(
    reservation_id: int,
    request: ReservationStatusRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[ReservationResponse]:
    data = await reservation_service.update_reservation_status(
        db, current_user, reservation_id, request.status
    )
    return BaseResponse[ReservationResponse].success(
        data=data,
        message={1: "预约已通过", 2: "预约已拒绝", 3: "预约已取消"}[request.status],
    )
