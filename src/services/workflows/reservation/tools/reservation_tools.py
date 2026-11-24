"""Read-only application and approval tools. Confirmation is HTTP-only."""
import json
from datetime import date, time
from typing import Literal
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from models.user import User
from models.reservation import Reservation
from models.lab import Lab
from models.equipment import Equipment
from schemas.reservation import ReservationCreateRequest, ReservationResponse
from services import reservation_service
from services.reservation_card_service import sign_card
from services.workflows.laboratory.agents import laboratory_agent
from core.exceptions import AppException


async def actor(context, role):
    if context.get("user_role") != role:
        return None
    user = await context["db"].get(User, context["user_id"])
    return user if user and user.role == role and user.status == 1 else None


@tool
async def consult_laboratory(runtime: ToolRuntime[dict], request: str) -> str:
    """Ask the shared laboratory agent to find labs/equipment, compare resources and clarify names/codes before application."""
    if await actor(runtime.context, "student") is None:
        return "只有学生可以使用预约申请资源查询。"
    result = await laboratory_agent.run([*runtime.context["messages"], HumanMessage(content=request)],
        db=runtime.context["db"], enable_thinking=runtime.context["enable_thinking"])
    runtime.context["resource_consulted"] = True
    return result


@tool(return_direct=True)
async def prepare_application(
    runtime: ToolRuntime[dict], lab_code: str, reservation_date: date,
    start_time: time, end_time: time, equipment_code: str | None = None, remark: str | None = None,
) -> str:
    """Student only. Resolve exact resource codes, validate schedule and conflicts, then generate a locked confirmation card. Never creates a reservation."""
    c = runtime.context
    user = await actor(c, "student")
    if user is None:
        return "只有已登录且启用的学生可以申请预约。"
    if not c.get("resource_consulted"):
        return "请先调用 consult_laboratory 查询并确认资源，再生成预约卡片。"
    lab = await c["db"].scalar(select(Lab).where(Lab.lab_code == lab_code))
    if lab is None:
        return "未找到实验室，请先查询并确认实验室编号。"
    equipment = None
    if equipment_code:
        equipment = await c["db"].scalar(select(Equipment).where(Equipment.code == equipment_code))
        if equipment is None:
            return "未找到设备，请先确认设备编号。"
    try:
        request = ReservationCreateRequest(lab_id=lab.id, equipment_id=equipment.id if equipment else None,
            date=reservation_date, start_time=start_time, end_time=end_time, remark=remark)
        await reservation_service.validate_application(c["db"], user, request)
    except AppException as exc:
        return exc.message
    except ValueError:
        return "预约日期或时间无效，请重新提供。"
    data = request.model_dump(mode="json")
    result = json.dumps({"type": "reservation_application", "editable": False,
        "data": data, "display": {"lab_name": lab.name, "equipment_name": equipment.name if equipment else None},
        "token": sign_card(user.id, "application", data),
        "confirm_endpoint": "/api/v1/reservation/confirm-application"}, ensure_ascii=False)
    c["cards"].append(result)
    return result


@tool
async def search_approvals(runtime: ToolRuntime[dict], status: Literal[0, 1, 2, 3] | None = 0,
    page_number: int = 1, reservation_id: int | None = None) -> dict:
    """Admin only. Query pending(0), approved(1), rejected(2), cancelled(3) reservations, or exact ID. Pagination is 20 per page."""
    c = runtime.context
    user = await actor(c, "admin")
    if user is None:
        return {"error": "permission_denied"}
    if page_number < 1:
        return {"error": "invalid_page"}
    if reservation_id is not None:
        item = await c["db"].scalar(select(Reservation).where(Reservation.id == reservation_id).options(
            joinedload(Reservation.user), joinedload(Reservation.lab), joinedload(Reservation.equipment)))
        return {"items": [ReservationResponse.model_validate(item).model_dump(mode="json")] if item else []}
    result = await reservation_service.get_reservation_page(c["db"], user, page_number, 20, status)
    return result.model_dump(mode="json")


@tool(return_direct=True)
async def prepare_approval(runtime: ToolRuntime[dict], reservation_id: int) -> str:
    """Admin only. Generate an immutable pending reservation card with approve/reject buttons; never approve or reject via language/tool call."""
    c = runtime.context
    user = await actor(c, "admin")
    if user is None:
        return "只有管理员可以审核预约。"
    item = await c["db"].scalar(select(Reservation).where(Reservation.id == reservation_id).options(
        joinedload(Reservation.user), joinedload(Reservation.lab), joinedload(Reservation.equipment)))
    if item is None or item.status != 0:
        return "未找到待审核的预约，请重新查询。"
    result = json.dumps({"type": "reservation_approval", "editable": False,
        "data": ReservationResponse.model_validate(item).model_dump(mode="json"),
        "actions": ["approve", "reject"], "token": sign_card(user.id, "approval", {"reservation_id": item.id}),
        "confirm_endpoint": "/api/v1/reservation/confirm-approval"}, ensure_ascii=False)
    c["cards"].append(result)
    return result


async def resolve_application_resource(context, *, lab_keyword=None, equipment_keyword=None):
    """Resolve only exact user identifiers; ambiguous results require a user choice."""
    from sqlalchemy import or_
    if await actor(context, "student") is None:
        return {"error": "permission_denied", "message": "只有学生可以申请预约。"}
    db = context["db"]
    lab = None
    if lab_keyword:
        labs = (await db.scalars(select(Lab).where(or_(Lab.name == lab_keyword, Lab.lab_code == lab_keyword)).limit(2))).all()
        if len(labs) != 1:
            return {"error": "ambiguous_resource", "message": "请根据查询结果明确选择实验室编号。"}
        lab = labs[0]
    equipment = None
    if equipment_keyword:
        query = select(Equipment).where(or_(Equipment.name == equipment_keyword, Equipment.code == equipment_keyword))
        if lab:
            query = query.where(Equipment.lab_id == lab.id)
        equipment_matches = (await db.scalars(query.limit(2))).all()
        if len(equipment_matches) != 1:
            return {"error": "ambiguous_resource", "message": "请根据查询结果明确选择设备编号及所属实验室。"}
        equipment = equipment_matches[0]
        lab = await db.get(Lab, equipment.lab_id)
    if lab is None:
        return {"error": "resource_not_found", "message": "未找到预约资源，请提供准确名称或编号。"}
    return {"lab_code": lab.lab_code, "equipment_code": equipment.code if equipment else None,
            "label": lab.name + (" / " + equipment.name if equipment else "")}


@tool
async def search_lab_availability(runtime: ToolRuntime[dict], date: date, start_time: time, end_time: time) -> dict:
    """查询时间段内被待审核或已通过预约占用的实验室。"""
    c = runtime.context
    rows = (await c["db"].execute(select(Reservation).where(
        Reservation.date == date, Reservation.status.in_([0, 1]),
        Reservation.start_time < end_time, Reservation.end_time > start_time,
    ).options(joinedload(Reservation.lab)))).scalars().all()
    return {"date": str(date), "start_time": str(start_time), "end_time": str(end_time),
            "occupied": [{"reservation_id": r.id, "lab_name": r.lab.name,
                          "start_time": str(r.start_time), "end_time": str(r.end_time),
                          "status": r.status} for r in rows]}


@tool
async def search_my_reservations(runtime: ToolRuntime[dict], date: date | None = None,
                                 cancellable_only: bool = False) -> list[dict]:
    """查询当前登录学生自己的预约；取消时只返回待审核记录。"""
    c = runtime.context
    user = await actor(c, "student")
    if user is None:
        return []
    query = select(Reservation).where(Reservation.user_id == user.id).options(joinedload(Reservation.lab))
    if date is not None:
        query = query.where(Reservation.date == date)
    if cancellable_only:
        query = query.where(Reservation.status == 0)
    rows = (await c["db"].execute(query.order_by(Reservation.date, Reservation.start_time))).scalars().all()
    status_names = {0: "待审核", 1: "已通过", 2: "已拒绝", 3: "已取消"}
    return [{"reservation_id": r.id, "lab_name": r.lab.name, "date": str(r.date),
             "start_time": str(r.start_time), "end_time": str(r.end_time),
             "status": r.status, "status_name": status_names.get(r.status, "未知")} for r in rows]


@tool(return_direct=True)
async def prepare_cancellation(runtime: ToolRuntime[dict], reservation_id: int) -> str:
    """为当前学生的预约生成取消确认卡片，不直接取消。"""
    c = runtime.context
    user = await actor(c, "student")
    if user is None:
        return "只有已登录且启用的学生可以取消预约。"
    item = await c["db"].scalar(select(Reservation).where(
        Reservation.id == reservation_id, Reservation.user_id == user.id).options(joinedload(Reservation.lab)))
    if item is None or item.status != 0:
        return "只有待审核的本人预约可以取消。"
    data = {"reservation_id": item.id}
    result = json.dumps({"type": "reservation_cancellation", "editable": False,
        "data": {"reservation_id": item.id, "lab_name": item.lab.name, "date": str(item.date),
                 "start_time": str(item.start_time), "end_time": str(item.end_time), "status": item.status},
        "actions": ["confirm_cancel"], "token": sign_card(user.id, "cancellation", data),
        "confirm_endpoint": "/api/v1/reservation/confirm-cancellation"}, ensure_ascii=False)
    c["cards"].append(result)
    return result
