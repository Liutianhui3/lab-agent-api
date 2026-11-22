"""Laboratory Workflow 使用的只读业务查询工具。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.lab import Lab
from schemas.equipment import EquipmentPageData, EquipmentResponse
from schemas.lab import LabPageData, LabResponse
from services import equipment_service, lab_service


async def list_laboratories(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    status: int | None = 1,
    page: int = 1,
    size: int = 20,
) -> LabPageData[LabResponse]:
    return await lab_service.get_lab_page(
        db, page, size, keyword=keyword, status=status
    )


async def list_equipment(
    db: AsyncSession,
    *,
    lab_id: int | None = None,
    keyword: str | None = None,
    status: int | None = 1,
    lab_status: int | None = None,
    page: int = 1,
    size: int = 20,
) -> EquipmentPageData[EquipmentResponse]:
    return await equipment_service.get_equipment_page(
        db,
        page,
        size,
        keyword=keyword,
        lab_id=lab_id,
        status=status,
        lab_status=lab_status,
    )


async def get_equipment_laboratories(
    db: AsyncSession,
    equipment: list[EquipmentResponse],
) -> dict[int, LabResponse]:
    lab_ids = {item.lab_id for item in equipment}
    if not lab_ids:
        return {}
    labs = await db.scalars(select(Lab).where(Lab.id.in_(lab_ids)))
    return {lab.id: LabResponse.model_validate(lab) for lab in labs}
