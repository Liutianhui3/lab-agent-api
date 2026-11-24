"""学生预约查询与取消 agent。"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware

from services.llm import llm_service
from services.workflows.reservation.tools import reservation_tools

PROMPT = """你是学生预约查询助手。只能查询当前登录学生自己的预约，或查询指定时间段哪些实验室被占用。
预约状态码：0=待审核，1=已通过，2=已拒绝，3=已取消。只有待审核(0)的预约允许取消；其他状态不得生成取消卡片。
用户要取消预约时，先查询本人待审核预约；目标唯一后调用 prepare_cancellation 生成确认卡片。不能直接取消。
用户明确说“第 N 条/序号 N”时，按本人预约查询结果的序号定位；明确说预约编号 N 时按 reservation_id 定位。
时间段占用查询调用 search_lab_availability。必须使用工具获取业务事实，不要猜测。"""


async def run(messages, *, context):
    context.setdefault("progress", []).append("understand_reservation_query")
    request_text = "\n".join(
        str(getattr(m, "content", ""))
        for m in messages
        if isinstance(getattr(m, "content", ""), str)
    )
    if "取消" in request_text:
        user = await reservation_tools.actor(context, "student")
        if user is None:
            return "只有已登录且启用的学生可以取消预约。"
        rows = await reservation_tools.search_my_reservations.coroutine(
            runtime=type("Runtime", (), {"context": context})(), date=None, cancellable_only=True
        )
        numbers = [
            int(n)
            for n in re.findall(r"(?:序号|第|预约编号|预约号)\s*(\d+)", request_text)
        ]
        chosen = None
        if numbers:
            number = numbers[-1]
            if re.search(r"(?:序号|第)\s*\d+", request_text):
                if 1 <= number <= len(rows):
                    chosen = rows[number - 1]
            else:
                chosen = next(
                    (row for row in rows if row["reservation_id"] == number), None
                )
        else:
            for row in rows:
                if row["lab_name"] in request_text:
                    if chosen is not None:
                        chosen = None
                        break
                    chosen = row
        if chosen is None:
            if len(rows) == 1:
                chosen = rows[0]
            elif rows:
                summary = "\n".join(
                    f"序号 {i}: 预约号 {row['reservation_id']}，{row['lab_name']}，{row['date']} {row['start_time']}-{row['end_time']}，状态 {row['status']}"
                    for i, row in enumerate(rows, 1)
                )
                return (
                    "请告诉我您要取消哪一条预约（可回复序号或实验室名称）：\n" + summary
                )
            else:
                return "没有查到可取消的本人预约。"
        card = await reservation_tools.prepare_cancellation.coroutine(
            runtime=type("Runtime", (), {"context": context})(),
            reservation_id=chosen["reservation_id"],
        )
        if context.get("cards"):
            context.setdefault("progress", []).append("prepare_cancellation")
            return context["cards"][-1]
        return card
    today = datetime.now(ZoneInfo("Asia/Shanghai"))
    agent = create_agent(
        model=llm_service.llm.bind(
            extra_body={"enable_thinking": context["enable_thinking"]}
        ),
        tools=[
            reservation_tools.search_lab_availability,
            reservation_tools.search_my_reservations,
            reservation_tools.prepare_cancellation,
        ],
        system_prompt=PROMPT + f"\n服务端当前上海时间：{today.isoformat()}。请将‘今天/明天/后天’转换为具体日期后再调用工具。",
        context_schema=dict,
        middleware=[ToolCallLimitMiddleware(run_limit=8)],
    )
    result = await agent.ainvoke(
        {"messages": list(messages)}, context=context, config={"recursion_limit": 24}
    )
    if context.get("cards"):
        context.setdefault("progress", []).append("prepare_cancellation")
        return context["cards"][-1]
    context.setdefault("progress", []).append("query_reservations")
    answer = result["messages"][-1].content
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    raise ValueError("预约查询 agent 返回空答案")
