"""不调用真实模型，验证图分支、结构化校验和 SSE 输出边界。"""

import unittest
from unittest.mock import AsyncMock, patch

from langchain.tools import ToolRuntime
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolCall
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.database import Base
from models.equipment import Equipment
from models.lab import Lab
from services.llm import llm_service
from services.workflows.laboratory.agents import laboratory_agent as laboratory
from services.workflows.laboratory.tools.laboratory_tools import search_laboratories
from services.workflows.supervisor import workflow
from services.workflows.supervisor.agents import supervisor_agent
from agent_fakes import call, model


class LaboratoryWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        engine = create_async_engine("sqlite+aiosqlite://")
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.db = AsyncSession(engine)
        self.addAsyncCleanup(self.db.close)
        self.db.add_all([
            Lab(id=1, name="纳米实验室", lab_code="LAB-1", location="A楼"),
            Lab(id=2, name="光学实验室", lab_code="LAB-2", location="B楼", status=0),
        ])
        await self.db.flush()
        self.db.add_all([
            Equipment(name="电子显微镜", code="EQ-1", lab_id=1, quantity=2),
            Equipment(name="电子显微镜", code="EQ-2", lab_id=2, status=0),
            Equipment(name="光谱仪", code="EQ-3", lab_id=2),
        ])
        await self.db.commit()

    async def test_equipment_ownership_includes_same_name_and_maintenance(self):
        messages = [HumanMessage(content="电子显微镜设备在哪个实验室下？")]
        reply_text = "- [电子显微镜](#resource-match)（EQ-1）：在[纳米实验室](#resource-match)（A楼），2 台，正常。\n- [电子显微镜](#resource-match)（EQ-2）：在[光学实验室](#resource-match)（B楼），1 台，维修。"
        agent = type("Agent", (), {
            "ainvoke": AsyncMock(return_value={"messages": [AIMessage(content=reply_text)]}),
        })()
        with patch.object(laboratory, "create_agent", return_value=agent):
            reply = await laboratory.run(messages, db=self.db)
        self.assertIn("EQ-1）", reply)
        self.assertIn("在[纳米实验室](#resource-match)（A楼）", reply)
        self.assertIn("在[光学实验室](#resource-match)（B楼）", reply)
        self.assertNotIn("光谱仪", reply)

    async def test_followup_sends_context_and_uses_device_code(self):
        messages = [
            HumanMessage(content="EQ-2 在哪个实验室？"),
            AIMessage(content="在光学实验室。"),
            HumanMessage(content="哪栋楼？"),
        ]
        agent = type("Agent", (), {
            "ainvoke": AsyncMock(return_value={"messages": [AIMessage(content="在 B 楼。")]}),
        })()
        with (
            patch.object(supervisor_agent.llm_service, "llm", model(
                call("query_resources", {"request": "EQ-2 在哪栋楼？"}), AIMessage(content="在 B 楼。"))),
            patch.object(laboratory, "create_agent", return_value=agent),
        ):
            reply = await workflow.run(messages, db=self.db)
        self.assertEqual(reply, "在 B 楼。")
        self.assertEqual(agent.ainvoke.await_args.args[0]["messages"][:len(messages)], messages)

    async def test_agent_response_preserves_requested_table_format(self):
        messages = [HumanMessage(content="用列表的形式列出来所有的实验室名称，容量，开放时间")]
        reply = "| 实验室名称 | 容量 | 开放时间 |\n| --- | --- | --- |\n| [纳米实验室](#resource-match) | 0 人 | 未登记 |"
        agent = type("Agent", (), {
            "ainvoke": AsyncMock(return_value={"messages": [AIMessage(content=reply)]}),
        })()
        with patch.object(laboratory, "create_agent", return_value=agent):
            reply = await laboratory.run(messages, db=self.db)
        lines = reply.splitlines()
        self.assertEqual(lines[:2], ["| 实验室名称 | 容量 | 开放时间 |", "| --- | --- | --- |"])
        self.assertIn("| [纳米实验室](#resource-match) | 0 人 | 未登记 |", lines)

    async def test_multi_lab_capacity_question_uses_tool_agent(self):
        messages = [HumanMessage(content="A实验室加上B实验室，一共最多能容纳多少人？")]
        agent = type("Agent", (), {
            "ainvoke": AsyncMock(return_value={"messages": [AIMessage(content="A 为 20 人，B 为 30 人，共 50 人。")]}),
        })()
        with patch.object(laboratory.llm_service, "llm") as model:
            model.bind.return_value = object()
            with patch.object(laboratory, "create_agent", return_value=agent) as create:
                response = await laboratory.run(messages, db=self.db, enable_thinking=True)
        self.assertEqual(response, "A 为 20 人，B 为 30 人，共 50 人。")
        self.assertEqual(create.call_args.kwargs["tools"], [laboratory.laboratory_tools.search_laboratories, laboratory.laboratory_tools.search_equipment])
        self.assertEqual(create.call_args.kwargs["middleware"][0].run_limit, 8)
        self.assertEqual(agent.ainvoke.await_args.kwargs["context"]["db"], self.db)
        model.bind.assert_called_once_with(extra_body={"enable_thinking": True})

    async def test_laboratory_search_tool_returns_capacity_for_name(self):
        self.db.add_all([
            Lab(name="飞秒超快激光光谱实验室", lab_code="FS-1", capacity=18),
            Lab(name="合成生物学智能温控实验室", lab_code="SB-1", capacity=26),
        ])
        await self.db.commit()
        runtime = ToolRuntime(
            state={}, context={"db": self.db}, config={}, stream_writer=None,
            tool_call_id=None, store=None,
        )
        first = await search_laboratories.coroutine(
            runtime=runtime, keyword="飞秒超快激光光谱实验室"
        )
        second = await search_laboratories.coroutine(
            runtime=runtime, keyword="合成生物学智能温控实验室"
        )
        self.assertEqual(first["items"][0]["capacity"], 18)
        self.assertEqual(second["items"][0]["capacity"], 26)

    async def test_analysis_agent_can_call_search_tool_multiple_times(self):
        self.db.add_all([
            Lab(name="飞秒超快激光光谱实验室", lab_code="FS-1", capacity=18),
            Lab(name="合成生物学智能温控实验室", lab_code="SB-1", capacity=26),
        ])
        await self.db.commit()
        class ToolCapableFakeModel(GenericFakeChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

        model = ToolCapableFakeModel(
            messages=iter([
                AIMessage(content="", tool_calls=[ToolCall(
                    name="search_laboratories", args={"keyword": "飞秒超快激光光谱实验室"}, id="call-1",
                )]),
                AIMessage(content="", tool_calls=[ToolCall(
                    name="search_laboratories", args={"keyword": "合成生物学智能温控实验室"}, id="call-2",
                )]),
                AIMessage(content="飞秒超快激光光谱实验室 18 人，合成生物学智能温控实验室 26 人，合计 44 人。"),
            ])
        )
        with patch.object(laboratory.llm_service, "llm", model):
            response = await laboratory.run(
                [HumanMessage(content="飞秒超快激光光谱实验室加上合成生物学智能温控实验室，两个实验室合计容量")],
                db=self.db,
            )
        self.assertIn("合计 44 人", response)
