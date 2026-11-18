from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_current_user
from core.database import get_db
from models.user import User
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
def get_reservation_page(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    status: int | None = Query(default=None, ge=0, le=3),
) -> ReservationPageResponse[ReservationResponse]:
    data = reservation_service.get_reservation_page(
        db, current_user, page, size, status
    )
    return ReservationPageResponse[ReservationResponse](
        code=200, message="success", data=data
    )


@router.post("/create", response_model=BaseResponse[ReservationResponse])
def create_reservation(
    request: ReservationCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BaseResponse[ReservationResponse]:
    """登录用户创建预约。"""
    reservation = reservation_service.create_reservation(db, current_user, request)
    return BaseResponse[ReservationResponse].success(
        data=ReservationResponse.model_validate(reservation), message="预约成功，待审核"
    )


@router.patch("/{reservation_id}/status", response_model=BaseResponse[ReservationResponse])
def update_reservation_status(reservation_id: int, request: ReservationStatusRequest,
                              current_user: Annotated[User, Depends(get_current_user)],
                              db: Annotated[Session, Depends(get_db)]) -> BaseResponse[ReservationResponse]:
    data = reservation_service.update_reservation_status(db, current_user, reservation_id, request.status)
    return BaseResponse[ReservationResponse].success(data=data, message={1: "预约已通过", 2: "预约已拒绝", 3: "预约已取消"}[request.status])
