"""ReservationWorkflow chooses application/approval strictly by authenticated role."""
from services.workflows.reservation.agents import approval_agent
from services.workflows.reservation.agents import query_agent
from langchain_core.messages import HumanMessage
from services.workflows.reservation.workflows import application


# Public progress vocabulary for this business workflow. The supervisor only
# forwards these events and does not define reservation-specific wording.
TOOL_LABELS = {
    "extract_conditions": "提取预约日期、时间和资源条件",
    "query_resources": "查询实验室和设备资料",
    "resolve_resource": "确认唯一可预约资源",
    "validate_reservation": "校验开放时间和预约冲突",
    "prepare_application": "生成预约确认卡片",
    "understand_approval": "理解审批查询或审批请求",
    "search_approvals": "查询预约审批记录",
    "prepare_approval": "生成审批确认卡片",
    "understand_reservation_query": "理解预约查询或取消请求",
    "query_reservations": "查询预约记录或时间段占用",
    "prepare_cancellation": "生成取消确认卡片",
}


async def run(messages, *, db, user_id, user_role, enable_thinking=False, progress=None):
    if db is None or user_id is None:
        return "请登录后使用预约功能。"
    if user_role not in {"student", "admin"}:
        raise ValueError("未知用户角色")
    context = {"db": db, "user_id": user_id, "user_role": user_role,
        "enable_thinking": enable_thinking, "messages": list(messages), "cards": [],
        "progress": progress if progress is not None else []}
    if user_role == "student":
        # Route by the current turn; old history may contain words such as
        # "占用" even when the new request is an application.
        current = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        text = str(getattr(current, "content", "")).lower()
        query_terms = ("占用", "使用", "取消", "预约记录", "预约情况")
        handler = query_agent if any(term in text for term in query_terms) else application
    else:
        handler = approval_agent
    return await handler.run(messages, context=context)
