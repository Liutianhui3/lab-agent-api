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
from services.reservation_card_service import CardConfirmation, ApprovalConfirmation, read_card

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
    """学生创建预约；聊天确认卡片使用 confirm-application。"""
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


@router.post("/confirm-application", response_model=BaseResponse[ReservationResponse])
async def confirm_application(
    request: CardConfirmation, current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
):
    """Confirm signed values only; client cannot override resource/time/owner fields."""
    data = read_card(request.token, current_user.id, "application")
    reservation = await reservation_service.create_reservation(db, current_user, ReservationCreateRequest.model_validate(data))
    return BaseResponse[ReservationResponse].success(
        data=ReservationResponse.model_validate(reservation), message="预约成功，待审核")


@router.post("/confirm-approval", response_model=BaseResponse[ReservationResponse])
async def confirm_approval(
    request: ApprovalConfirmation, current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
):
    from core.exceptions import AppException
    if current_user.role != "admin" or current_user.status != 1 or request.decision not in (1, 2):
        raise AppException(code=4030, message="无权审核或审核决定无效", status_code=403)
    data = read_card(request.token, current_user.id, "approval")
    result = await reservation_service.update_reservation_status(db, current_user, data["reservation_id"], request.decision)
    return BaseResponse[ReservationResponse].success(data=result, message="预约已通过" if request.decision == 1 else "预约已拒绝")


@router.post("/confirm-cancellation", response_model=BaseResponse[ReservationResponse])
async def confirm_cancellation(
    request: CardConfirmation, current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
):
    from core.exceptions import AppException
    if current_user.role != "student" or current_user.status != 1:
        raise AppException(code=4030, message="只有学生可以取消预约", status_code=403)
    data = read_card(request.token, current_user.id, "cancellation")
    result = await reservation_service.update_reservation_status(db, current_user, data["reservation_id"], 3)
    return BaseResponse[ReservationResponse].success(data=result, message="预约已取消")
