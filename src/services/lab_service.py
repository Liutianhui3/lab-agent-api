from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.exceptions import AppException
from models.lab import Lab
from schemas.lab import LabCreateRequest, LabPageData, LabResponse, LabUpdateRequest


def _is_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    return (
        getattr(original, "args", (None,))[0] == 1062
        or getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE"
    )


def get_lab_page(
    db: Session,
    page: int,
    size: int,
    keyword: str | None = None,
    status: int | None = None,
) -> LabPageData[LabResponse]:
    """分页查询实验室，并返回全局状态和容量统计。"""
    query = select(Lab)
    count_query = select(func.count()).select_from(Lab)

    if status is not None:
        query = query.where(Lab.status == status)
        count_query = count_query.where(Lab.status == status)

    search = keyword.strip() if keyword else ""
    if search:
        pattern = f"%{search}%"
        conditions = or_(
            Lab.lab_code.ilike(pattern),
            Lab.name.ilike(pattern),
            Lab.location.ilike(pattern),
        )
        query = query.where(conditions)
        count_query = count_query.where(conditions)

    total = db.scalar(count_query) or 0
    global_total = db.scalar(select(func.count()).select_from(Lab)) or 0
    open_count = db.scalar(
        select(func.count()).select_from(Lab).where(Lab.status == 1)
    ) or 0
    closed_count = db.scalar(
        select(func.count()).select_from(Lab).where(Lab.status == 0)
    ) or 0
    total_capacity = db.scalar(select(func.coalesce(func.sum(Lab.capacity), 0))) or 0

    labs = db.scalars(
        query.order_by(Lab.created_at.desc(), Lab.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return LabPageData(
        total=total,
        items=[LabResponse.model_validate(lab) for lab in labs],
        page=page,
        size=size,
        global_total=global_total,
        open_count=open_count,
        closed_count=closed_count,
        total_capacity=total_capacity,
    )


def create_lab(db: Session, request: LabCreateRequest) -> LabResponse:
    """创建实验室。"""
    if db.scalar(select(Lab.id).where(Lab.lab_code == request.lab_code)) is not None:
        raise AppException(code=4008, message="实验室编号已存在", status_code=409)

    lab = Lab(**request.model_dump())
    try:
        db.add(lab)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _is_unique_violation(error):
            raise AppException(
                code=4008, message="实验室编号已存在", status_code=409
            ) from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(lab)
    return LabResponse.model_validate(lab)


def update_lab(db: Session, lab_id: int, request: LabUpdateRequest) -> LabResponse:
    """更新实验室；未提交的字段不变，可空字段显式传 null 表示清空。"""
    lab = db.get(Lab, lab_id)
    if lab is None:
        raise AppException(code=4040, message="实验室不存在", status_code=404)

    updates = request.model_dump(exclude_unset=True)
    if not updates:
        return LabResponse.model_validate(lab)

    lab_code = updates.get("lab_code")
    if lab_code is not None and db.scalar(
        select(Lab.id).where(Lab.lab_code == lab_code, Lab.id != lab_id)
    ) is not None:
        raise AppException(code=4008, message="实验室编号已存在", status_code=409)

    try:
        for field, value in updates.items():
            setattr(lab, field, value)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _is_unique_violation(error):
            raise AppException(
                code=4008, message="实验室编号已存在", status_code=409
            ) from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(lab)
    return LabResponse.model_validate(lab)


def delete_lab(db: Session, lab_id: int) -> None:
    """只允许删除关闭状态的实验室。"""
    try:
        result = db.execute(delete(Lab).where(Lab.id == lab_id, Lab.status == 0))
        if result.rowcount == 0:
            if db.get(Lab, lab_id) is None:
                raise AppException(code=4040, message="实验室不存在", status_code=404)
            raise AppException(
                code=4003,
                message="只有关闭状态的实验室才允许删除",
                status_code=400,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
