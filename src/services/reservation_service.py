from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from core.exceptions import AppException
from models.equipment import Equipment
from models.lab import Lab
from models.reservation import Reservation
from models.user import User
from schemas.reservation import ReservationCreateRequest, ReservationPageData, ReservationResponse


def get_reservation_page(
    db: Session, current_user: User, page: int, size: int, status: int | None = None
) -> ReservationPageData[ReservationResponse]:
    """分页查询预约；管理员查看全部，普通用户仅查看自己的预约。"""
    base = select(Reservation)
    count_base = select(func.count()).select_from(Reservation)
    if current_user.role != "admin":
        base = base.where(Reservation.user_id == current_user.id)
        count_base = count_base.where(Reservation.user_id == current_user.id)
    if status is not None:
        base = base.where(Reservation.status == status)
        count_base = count_base.where(Reservation.status == status)

    total = db.scalar(count_base) or 0
    stats_query = select(Reservation.status, func.count()).group_by(Reservation.status)
    if current_user.role != "admin":
        stats_query = stats_query.where(Reservation.user_id == current_user.id)
    stats = {row[0]: row[1] for row in db.execute(stats_query)}
    reservations = db.scalars(
        base.options(joinedload(Reservation.user), joinedload(Reservation.lab), joinedload(Reservation.equipment))
        .order_by(Reservation.date.desc(), Reservation.start_time.desc(), Reservation.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return ReservationPageData(
        total=total,
        items=[ReservationResponse.model_validate(item) for item in reservations],
        page=page,
        size=size,
        pending_count=stats.get(0, 0),
        approved_count=stats.get(1, 0),
        rejected_count=stats.get(2, 0),
        cancelled_count=stats.get(3, 0),
    )


def update_reservation_status(db: Session, current_user: User, reservation_id: int, target_status: int) -> ReservationResponse:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise AppException(code=4040, message="预约不存在", status_code=404)
    if target_status == 3:
        if reservation.user_id != current_user.id:
            raise AppException(code=4030, message="只能取消自己的预约", status_code=403)
        if reservation.status not in (0, 1):
            raise AppException(code=4000, message="当前预约状态不可取消", status_code=400)
    elif target_status in (1, 2):
        if current_user.role != "admin":
            raise AppException(code=4030, message="只有管理员可以审核预约", status_code=403)
        if reservation.status != 0:
            raise AppException(code=4000, message="只有待审核预约可以审核", status_code=400)
    else:
        raise AppException(code=4000, message="无效的预约状态", status_code=400)
    if target_status == 1:
        # 实验室预约与同实验室所有预约冲突；设备预约只与实验室预约或同设备预约冲突。
        resource_conflict = (
            Reservation.id.is_not(None)
            if reservation.equipment_id is None
            else Reservation.equipment_id.is_(None)
        )
        if reservation.equipment_id is not None:
            resource_conflict = or_(
                Reservation.equipment_id.is_(None),
                Reservation.equipment_id == reservation.equipment_id,
            )
        conflict = db.scalar(
            select(Reservation.id)
            .where(
                Reservation.id != reservation.id,
                Reservation.lab_id == reservation.lab_id,
                Reservation.date == reservation.date,
                Reservation.status == 1,
                Reservation.start_time < reservation.end_time,
                Reservation.end_time > reservation.start_time,
                resource_conflict,
            )
            .limit(1)
        )
        if conflict is not None:
            raise AppException(
                code=4008, message="预约时段已被其他已通过预约占用", status_code=409
            )
    try:
        reservation.status = target_status
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(reservation)
    db.refresh(reservation, attribute_names=["user", "lab", "equipment"])
    return ReservationResponse.model_validate(reservation)


def create_reservation(
    db: Session, current_user: User, request: ReservationCreateRequest
) -> Reservation:
    """创建待审核预约；以实验室行锁串行化同实验室的预约检查和写入。

    待审核、已通过的预约占用资源；相邻时段允许预约。
    未配置的开放时间边界不作限制，不支持跨日预约。
    """
    try:
        if current_user.status != 1:
            raise AppException(code=4030, message="用户已被禁用", status_code=403)
        if request.start_time.tzinfo is not None or request.end_time.tzinfo is not None:
            raise AppException(
                code=4000, message="预约时间请使用不带时区的本地时间", status_code=400
            )
        if request.start_time >= request.end_time:
            raise AppException(
                code=4000, message="开始时间必须早于结束时间", status_code=400
            )
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        if request.date < today:
            raise AppException(
                code=4000, message="预约日期不能早于当前日期", status_code=400
            )

        lab = db.scalar(
            select(Lab)
            .where(Lab.id == request.lab_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if lab is None:
            raise AppException(code=4040, message="实验室不存在", status_code=404)
        if lab.status != 1:
            raise AppException(code=4003, message="实验室未开放，无法预约", status_code=400)
        if lab.open_time is not None and request.start_time < lab.open_time:
            raise AppException(
                code=4000, message="预约开始时间早于实验室开放时间", status_code=400
            )
        if lab.close_time is not None and request.end_time > lab.close_time:
            raise AppException(
                code=4000, message="预约结束时间晚于实验室关闭时间", status_code=400
            )

        if request.equipment_id is not None:
            equipment = db.scalar(
                select(Equipment)
                .where(Equipment.id == request.equipment_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if equipment is None:
                raise AppException(code=4040, message="设备不存在", status_code=404)
            if equipment.lab_id != lab.id:
                raise AppException(
                    code=4000, message="设备不属于所选实验室", status_code=400
                )
            if equipment.status != 1 or equipment.quantity <= 0:
                raise AppException(
                    code=4003, message="设备当前不可预约", status_code=400
                )

        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        if datetime.combine(request.date, request.start_time) <= now:
            raise AppException(
                code=4000, message="预约开始时间必须晚于当前时间", status_code=400
            )

        conflict_query = select(Reservation.id).where(
            Reservation.lab_id == lab.id,
            Reservation.date == request.date,
            Reservation.status.in_((0, 1)),
            Reservation.start_time < request.end_time,
            Reservation.end_time > request.start_time,
        )
        if request.equipment_id is not None:
            conflict_query = conflict_query.where(
                or_(
                    Reservation.equipment_id.is_(None),
                    Reservation.equipment_id == request.equipment_id,
                )
            )
        # 锁定读读取最新已提交记录，避免 MySQL 可重复读快照漏掉并发预约。
        if db.scalar(conflict_query.limit(1).with_for_update()) is not None:
            raise AppException(
                code=4008, message="所选时段已被预约，请选择其他时段", status_code=409
            )

        reservation = Reservation(
            user_id=current_user.id, status=0, **request.model_dump()
        )
        db.add(reservation)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(reservation)
    db.refresh(
        reservation,
        attribute_names=["user", "lab", "equipment"],
    )
    return reservation
