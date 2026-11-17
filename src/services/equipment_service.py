from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.exceptions import AppException
from models.equipment import Equipment
from models.lab import Lab
from schemas.equipment import (
    EquipmentCreateRequest,
    EquipmentPageData,
    EquipmentResponse,
    EquipmentUpdateRequest,
)


def _is_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    return (
        getattr(original, "args", (None,))[0] == 1062
        or getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE"
    )


def get_equipment_page(
    db: Session,
    page: int,
    size: int,
    keyword: str | None = None,
    lab_id: int | None = None,
    status: int | None = None,
) -> EquipmentPageData[EquipmentResponse]:
    """分页查询设备，并返回不受筛选条件影响的全局统计。"""
    query = select(Equipment)
    count_query = select(func.count()).select_from(Equipment)

    if lab_id is not None:
        query = query.where(Equipment.lab_id == lab_id)
        count_query = count_query.where(Equipment.lab_id == lab_id)
    if status is not None:
        query = query.where(Equipment.status == status)
        count_query = count_query.where(Equipment.status == status)

    search = keyword.strip() if keyword else ""
    if search:
        pattern = f"%{search}%"
        conditions = or_(Equipment.code.ilike(pattern), Equipment.name.ilike(pattern))
        query = query.where(conditions)
        count_query = count_query.where(conditions)

    total = db.scalar(count_query) or 0
    global_total = db.scalar(select(func.count()).select_from(Equipment)) or 0
    normal_count = db.scalar(
        select(func.count()).select_from(Equipment).where(Equipment.status == 1)
    ) or 0
    maintenance_count = db.scalar(
        select(func.count()).select_from(Equipment).where(Equipment.status == 0)
    ) or 0
    total_quantity = db.scalar(select(func.coalesce(func.sum(Equipment.quantity), 0))) or 0

    equipments = db.scalars(
        query.order_by(Equipment.created_at.desc(), Equipment.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return EquipmentPageData(
        total=total,
        items=[EquipmentResponse.model_validate(item) for item in equipments],
        page=page,
        size=size,
        global_total=global_total,
        normal_count=normal_count,
        maintenance_count=maintenance_count,
        total_quantity=total_quantity,
    )


def create_equipment(db: Session, request: EquipmentCreateRequest) -> EquipmentResponse:
    """创建设备。"""
    if db.get(Lab, request.lab_id) is None:
        raise AppException(code=4040, message="所属实验室不存在", status_code=404)
    if db.scalar(select(Equipment.id).where(Equipment.code == request.code)) is not None:
        raise AppException(code=4008, message="设备编号已存在", status_code=409)

    equipment = Equipment(**request.model_dump())
    try:
        db.add(equipment)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _is_unique_violation(error):
            raise AppException(code=4008, message="设备编号已存在", status_code=409) from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(equipment)
    return EquipmentResponse.model_validate(equipment)


def update_equipment(
    db: Session, equipment_id: int, request: EquipmentUpdateRequest
) -> EquipmentResponse:
    """更新指定设备；未传字段保持不变，可空字段显式传 null 表示清空。"""
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise AppException(code=4040, message="设备不存在", status_code=404)

    updates = request.model_dump(exclude_unset=True)
    if not updates:
        return EquipmentResponse.model_validate(equipment)

    lab_id = updates.get("lab_id")
    if lab_id is not None and db.get(Lab, lab_id) is None:
        raise AppException(code=4040, message="所属实验室不存在", status_code=404)
    code = updates.get("code")
    if code is not None and db.scalar(
        select(Equipment.id).where(Equipment.code == code, Equipment.id != equipment_id)
    ) is not None:
        raise AppException(code=4008, message="设备编号已存在", status_code=409)

    try:
        for field, value in updates.items():
            setattr(equipment, field, value)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _is_unique_violation(error):
            raise AppException(code=4008, message="设备编号已存在", status_code=409) from error
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(equipment)
    return EquipmentResponse.model_validate(equipment)


def delete_equipment(db: Session, equipment_id: int) -> None:
    """删除指定设备。"""
    try:
        result = db.execute(delete(Equipment).where(Equipment.id == equipment_id))
        if result.rowcount == 0:
            raise AppException(code=4040, message="设备不存在", status_code=404)
        db.commit()
    except Exception:
        db.rollback()
        raise
