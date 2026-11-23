"""Laboratory Workflow 使用的只读业务查询工具。"""

from typing import Literal

from langchain.tools import ToolRuntime, tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.lab import Lab
from schemas.equipment import EquipmentResponse
from schemas.lab import LabResponse
from services import equipment_service, lab_service


@tool
async def search_laboratories(
    runtime: ToolRuntime[dict],
    keyword: str | None = None,
    status: Literal["open", "closed", "all"] = "all",
    page_number: int = 1,
) -> dict:
    """Search labs by name or code, or list all labs when keyword is empty. Returns names, codes, capacities, locations, opening hours, statuses, total count, and page."""
    status_value = {"open": 1, "closed": 0, "all": None}[status]
    result = await lab_service.get_lab_page(
        runtime.context["db"], page=page_number, size=50, keyword=keyword, status=status_value
    )
    return {
        "total": result.total,
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "code": item.lab_code,
                "capacity": item.capacity,
                "location": item.location,
                "status": item.status,
                "open_time": item.open_time.isoformat() if item.open_time else None,
                "close_time": item.close_time.isoformat() if item.close_time else None,
                "description": item.description,
            }
            for item in result.items
        ],
        "page": result.page,
        "size": result.size,
        "truncated": result.total > len(result.items),
    }


@tool
async def search_equipment(
    runtime: ToolRuntime[dict],
    keyword: str | None = None,
    lab_keyword: str | None = None,
    status: Literal["normal", "maintenance", "all"] = "all",
    lab_status: Literal["open", "closed", "all"] = "all",
    page_number: int = 1,
) -> dict:
    """Search equipment by name/code, optionally filtered by its laboratory and equipment/lab status. Empty keyword lists equipment."""
    db = runtime.context["db"]
    lab_id = None
    labs_total = None
    if lab_keyword:
        labs = await lab_service.get_lab_page(
            db, page=1, size=50, keyword=lab_keyword,
            status={"open": 1, "closed": 0, "all": None}[lab_status],
        )
        matches = [lab for lab in labs.items if lab.name == lab_keyword or lab.lab_code == lab_keyword]
        if len(matches) == 1:
            lab_id = matches[0].id
        elif labs.total != 1:
            return {
                "outcome": "laboratory_not_found" if labs.total == 0 else "ambiguous_laboratory",
                "total": labs.total,
                "items": [{"name": lab.name, "code": lab.lab_code} for lab in labs.items],
            }
        else:
            lab_id = labs.items[0].id
        labs_total = labs.total
    result = await equipment_service.get_equipment_page(
        db, page=page_number, size=50, keyword=keyword, lab_id=lab_id,
        status={"normal": 1, "maintenance": 0, "all": None}[status],
        lab_status={"open": 1, "closed": 0, "all": None}[lab_status],
    )
    owners = await get_equipment_laboratories(db, result.items)
    return {
        "total": result.total,
        "page": result.page,
        "size": result.size,
        "truncated": result.total > len(result.items),
        "laboratory_matches": labs_total,
        "items": [
            {
                "name": item.name,
                "code": item.code,
                "quantity": item.quantity,
                "status": item.status,
                "specification": item.sepc,
                "description": item.description,
                "laboratory": ({
                    "name": owners[item.lab_id].name,
                    "code": owners[item.lab_id].lab_code,
                    "location": owners[item.lab_id].location,
                    "status": owners[item.lab_id].status,
                } if item.lab_id in owners else None),
            }
            for item in result.items
        ],
    }
async def get_equipment_laboratories(
    db: AsyncSession,
    equipment: list[EquipmentResponse],
) -> dict[int, LabResponse]:
    lab_ids = {item.lab_id for item in equipment}
    if not lab_ids:
        return {}
    labs = await db.scalars(select(Lab).where(Lab.id.in_(lab_ids)))
    return {lab.id: LabResponse.model_validate(lab) for lab in labs}
