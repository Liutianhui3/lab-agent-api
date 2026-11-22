from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AppException
from models.equipment import Equipment
from models.lab import Lab
from schemas.lab import LabCreateRequest, LabPageData, LabResponse, LabUpdateRequest


def _is_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    return (
        getattr(original, "args", (None,))[0] == 1062
        or getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE"
    )


def _lab_filters(keyword: str | None, status: int | None) -> list:
    filters = []
    if status is not None:
        filters.append(Lab.status == status)
    search = keyword.strip() if keyword else ""
    if search:
        filters.append(or_(
            Lab.lab_code.icontains(search, autoescape=True),
            Lab.name.icontains(search, autoescape=True),
            Lab.location.icontains(search, autoescape=True),
        ))
    return filters


async def get_all_labs(
    db: AsyncSession, *, keyword: str | None = None, status: int | None = None,
) -> list[LabResponse]:
    labs = await db.scalars(select(Lab).where(*_lab_filters(keyword, status)).order_by(Lab.lab_code))
    return [LabResponse.model_validate(lab) for lab in labs]


async def get_lab_page(
    db: AsyncSession,
    page: int,
    size: int,
    keyword: str | None = None,
    status: int | None = None,
) -> LabPageData[LabResponse]:
    """分页查询实验室，并返回全局状态和容量统计。"""
    filters = _lab_filters(keyword, status)
    query = select(Lab).where(*filters)
    count_query = select(func.count()).select_from(Lab).where(*filters)

    total = await db.scalar(count_query) or 0
    global_total = await db.scalar(select(func.count()).select_from(Lab)) or 0
    open_count = (
        await db.scalar(select(func.count()).select_from(Lab).where(Lab.status == 1))
        or 0
    )
    closed_count = (
        await db.scalar(select(func.count()).select_from(Lab).where(Lab.status == 0))
        or 0
    )
    total_capacity = (
        await db.scalar(select(func.coalesce(func.sum(Lab.capacity), 0))) or 0
    )

    labs = (
        await db.scalars(
            query.order_by(Lab.created_at.desc(), Lab.id)
            .offset((page - 1) * size)
            .limit(size)
        )
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


async def get_lab_by_code(db: AsyncSession, lab_code: str) -> LabResponse:
    """按业务编号精确查询实验室。"""
    lab = await db.scalar(select(Lab).where(Lab.lab_code == lab_code))
    if lab is None:
        raise AppException(code=4040, message="实验室不存在", status_code=404)
    return LabResponse.model_validate(lab)


async def create_lab(db: AsyncSession, request: LabCreateRequest) -> LabResponse:
    """创建实验室。"""
    if (
        await db.scalar(select(Lab.id).where(Lab.lab_code == request.lab_code))
        is not None
    ):
        raise AppException(code=4008, message="实验室编号已存在", status_code=409)

    lab = Lab(**request.model_dump())
    try:
        db.add(lab)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if _is_unique_violation(error):
            raise AppException(
                code=4008, message="实验室编号已存在", status_code=409
            ) from error
        raise
    except Exception:
        await db.rollback()
        raise
    await db.refresh(lab)
    return LabResponse.model_validate(lab)


async def update_lab(
    db: AsyncSession, lab_id: int, request: LabUpdateRequest
) -> LabResponse:
    """更新实验室；未提交的字段不变，可空字段显式传 null 表示清空。"""
    lab = await db.get(Lab, lab_id)
    if lab is None:
        raise AppException(code=4040, message="实验室不存在", status_code=404)

    updates = request.model_dump(exclude_unset=True)
    if not updates:
        return LabResponse.model_validate(lab)

    lab_code = updates.get("lab_code")
    if (
        lab_code is not None
        and await db.scalar(
            select(Lab.id).where(Lab.lab_code == lab_code, Lab.id != lab_id)
        )
        is not None
    ):
        raise AppException(code=4008, message="实验室编号已存在", status_code=409)

    try:
        for field, value in updates.items():
            setattr(lab, field, value)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if _is_unique_violation(error):
            raise AppException(
                code=4008, message="实验室编号已存在", status_code=409
            ) from error
        raise
    except Exception:
        await db.rollback()
        raise
    await db.refresh(lab)
    return LabResponse.model_validate(lab)


async def delete_lab(db: AsyncSession, lab_id: int) -> None:
    """只允许删除关闭且未关联设备的实验室。"""
    try:
        lab = await db.get(Lab, lab_id)
        if lab is None:
            raise AppException(code=4040, message="实验室不存在", status_code=404)
        if lab.status != 0:
            raise AppException(
                code=4003,
                message="只有关闭状态的实验室才允许删除",
                status_code=400,
            )
        if (
            await db.scalar(select(Equipment.id).where(Equipment.lab_id == lab_id))
            is not None
        ):
            raise AppException(
                code=4004,
                message="实验室仍关联设备，无法删除",
                status_code=400,
            )
        await db.execute(delete(Lab).where(Lab.id == lab_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
