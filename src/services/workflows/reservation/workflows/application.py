"""预约申请图：agent 理解请求，StateGraph 控制业务顺序。"""
from datetime import datetime
from types import SimpleNamespace
from typing import Any, TypedDict
from zoneinfo import ZoneInfo
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import END, StateGraph
from schemas.reservation import ReservationApplicationDraft
from services.llm import llm_service
from services.workflows.reservation.tools import reservation_tools

EXTRACT_PROMPT = """你是预约条件理解助手，只负责从用户请求和历史中提取预约条件，不执行任何操作。
不猜测未提供的日期、开始时间、结束时间、实验室或设备；名称和编号只填写用户明确说出的值。
根据系统当前上海时间解释相对日期，结合历史补齐已明确条件，最新更改优先。
不能代他人申请；要求审批、查询他人预约或管理员申请时填写 clarification。
有跨日或多个预约需求时填写 clarification 请用户分开申请；没有澄清事项时 clarification 必须为 null，不要填写“无”。"""

_EMPTY_CLARIFICATIONS = {"", "无", "没有", "无。", "none", "null", "n/a"}

def _clarification(value):
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _EMPTY_CLARIFICATIONS else text

class ApplicationState(TypedDict, total=False):
    messages: list[BaseMessage]
    context: dict[str, Any]
    draft: ReservationApplicationDraft
    resource: dict[str, Any]
    resource_answer: str
    result: str

def _agent(context):
    return create_agent(model=llm_service.llm.bind(extra_body={"enable_thinking": context["enable_thinking"]}),
        tools=[], system_prompt=EXTRACT_PROMPT, response_format=ReservationApplicationDraft,
        context_schema=dict)

async def extract_conditions(messages, *, enable_thinking=False):
    """Compatibility entry point for callers/tests; understanding remains agent-backed."""
    context = {"enable_thinking": enable_thinking}
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    result = await _agent(context).ainvoke(
        {"messages": [SystemMessage(content=EXTRACT_PROMPT + f"\n服务端当前上海时间：{now.isoformat()}。请将相对日期转换为具体日期。"), *messages]},
        context=context,
    )
    draft = result.get("structured_response")
    if draft is None:
        raise ValueError("预约条件 agent 未返回结构化结果")
    normalized = ReservationApplicationDraft.model_validate(draft)
    # Reservation APIs use Shanghai wall-clock times without timezone offsets.
    if normalized.start_time is not None and normalized.start_time.tzinfo is not None:
        normalized.start_time = normalized.start_time.replace(tzinfo=None)
    if normalized.end_time is not None and normalized.end_time.tzinfo is not None:
        normalized.end_time = normalized.end_time.replace(tzinfo=None)
    return normalized

async def _understand(state):
    c = state["context"]
    draft = await extract_conditions(state["messages"], enable_thinking=c["enable_thinking"])
    return {"draft": draft}

def _route_understand(state):
    d = state["draft"]
    return "finish" if _clarification(d.clarification) or not (d.lab_keyword or d.equipment_keyword) else "query"

def _finish_understand(state):
    d = state["draft"]
    return {"result": _clarification(d.clarification) or "你想预约哪个实验室或设备？请提供名称或编号。"}

async def _query_resource(state):
    c, d = state["context"], state["draft"]
    c.setdefault("progress", []).append("query_resources")
    runtime = SimpleNamespace(context=c)
    answer = await reservation_tools.consult_laboratory.coroutine(runtime=runtime,
        request=f"查询预约资源，确认名称、编号、所属实验室：实验室={d.lab_keyword or '未指定'}；设备={d.equipment_keyword or '无'}。不要申请预约。")
    resource = await reservation_tools.resolve_application_resource(c, lab_keyword=d.lab_keyword, equipment_keyword=d.equipment_keyword)
    return {"resource_answer": answer, "resource": resource}

async def _resolve(state):
    c, r, d = state["context"], state["resource"], state["draft"]
    if r.get("error"):
        return {"result": r["message"] + "\n" + state["resource_answer"]}
    c.setdefault("progress", []).append("resolve_resource")
    missing = [label for value, label in [(d.date, "预约日期"), (d.start_time, "开始时间"), (d.end_time, "结束时间")] if value is None]
    if missing:
        return {"result": "已确认预约资源：" + r["label"] + "。请补充" + "、".join(missing) + "。"}
    return {}

async def _prepare(state):
    c, d, r = state["context"], state["draft"], state["resource"]
    c.setdefault("progress", []).extend(["validate_reservation", "prepare_application"])
    result = await reservation_tools.prepare_application.coroutine(runtime=SimpleNamespace(context=c),
        lab_code=r["lab_code"], equipment_code=r.get("equipment_code"), reservation_date=d.date,
        start_time=d.start_time, end_time=d.end_time, remark=d.remark)
    return {"result": result}

def _route_resolve(state):
    return "finish" if state.get("result") else "prepare"

def _build_graph():
    g = StateGraph(ApplicationState)
    for name, node in [("understand", _understand), ("finish_understand", _finish_understand), ("query_resource", _query_resource), ("resolve", _resolve), ("prepare", _prepare)]:
        g.add_node(name, node)
    g.set_entry_point("understand")
    g.add_conditional_edges("understand", _route_understand, {"finish": "finish_understand", "query": "query_resource"})
    g.add_edge("finish_understand", END); g.add_edge("query_resource", "resolve")
    g.add_conditional_edges("resolve", _route_resolve, {"finish": END, "prepare": "prepare"}); g.add_edge("prepare", END)
    return g.compile()

async def run(messages, *, context):
    if await reservation_tools.actor(context, "student") is None:
        return "只有已登录且启用的学生可以申请预约。"
    context.setdefault("progress", []).append("extract_conditions")
    state = await _build_graph().ainvoke({"messages": list(messages), "context": context})
    return state["result"]
