"""不调用真实模型，验证图分支、结构化校验和 SSE 输出边界。"""

import unittest
from datetime import time
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.database import Base
from models.equipment import Equipment
from models.lab import Lab
from schemas.agent import LaboratoryQuery, RouteDecision
from services.agent import workflow
from services.agent.workflows import laboratory
from services.llm import llm_service


class AgentWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_scope_response = llm_service.generate_scope_response
        self.reply_patch = patch.object(llm_service, "generate_scope_response", new_callable=AsyncMock)
        self.reply = self.reply_patch.start()
        self.reply.return_value = "我这里暂不提供写作服务，你可以通过系统页面查看实验室信息。"
        self.addCleanup(self.reply_patch.stop)

    async def test_out_of_scope_and_history_are_routed(self):
        messages = [HumanMessage(content="实验室有哪些？"), HumanMessage(content="写首诗")]
        with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
            classify.return_value = RouteDecision(intent="out_of_scope", route_reason="无关写作")
            result = await workflow.graph.ainvoke({"messages": messages})
        self.assertEqual(result["response"], self.reply.return_value)
        self.assertEqual(classify.await_args.args[0][1:], messages)
        classify.assert_awaited_once()

    async def test_all_supported_intents_do_not_invent_business_results(self):
        for intent in ("knowledge_qa", "resource_query", "availability_query", "reservation_query",
                       "create_reservation", "cancel_reservation", "unclear", "greeting"):
            with self.subTest(intent=intent):
                with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
                    classify.return_value = RouteDecision(intent=intent, route_reason="分类测试")
                    result = await workflow.run([HumanMessage(content="请求")])
                self.assertTrue(result)
                if intent not in ("unclear", "greeting"):
                    if intent == "resource_query":
                        self.assertIn("查询", result)
                    else:
                        self.assertNotEqual(result, "")

    async def test_invalid_classification_does_not_fall_back_to_unrestricted_chat(self):
        with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
            classify.return_value = {"intent": "execute_sql", "route_reason": "无效"}
            with self.assertRaises(ValidationError):
                await workflow.run([HumanMessage(content="请求")])

    async def test_router_failure_propagates(self):
        with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
            classify.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                await workflow.run([HumanMessage(content="请求")])

    async def test_stream_hides_classification(self):
        with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
            classify.return_value = RouteDecision(intent="out_of_scope", route_reason="内部分类依据")
            chunks = [chunk async for chunk in llm_service.stream_chat([HumanMessage(content="写首诗")])]
        self.assertEqual(chunks, [self.reply.return_value])

    async def test_empty_messages_rejected(self):
        with self.assertRaises(ValueError):
            await llm_service.chat([])

    async def test_classifier_uses_validated_function_calling(self):
        with patch.object(llm_service, "llm") as model:
            model.with_structured_output.return_value.ainvoke = AsyncMock(
                return_value={"intent": "greeting", "route_reason": "问候"}
            )
            result = await llm_service.classify_request([HumanMessage(content="你好")])
        self.assertEqual(result.intent, "greeting")
        model.with_structured_output.assert_called_once_with(RouteDecision, method="function_calling")

    async def test_thinking_flag_reaches_all_model_calls(self):
        messages = [HumanMessage(content="写首诗")]
        for enabled in (True, False):
            with self.subTest(enable_thinking=enabled):
                with patch.object(llm_service, "llm") as model:
                    router = model.with_structured_output.return_value
                    router.ainvoke = AsyncMock(return_value={
                        "intent": "out_of_scope", "route_reason": "无关请求",
                    })
                    model.ainvoke = AsyncMock(return_value=type("Reply", (), {"content": "范围说明"})())
                    with patch.object(llm_service, "generate_scope_response", self.original_scope_response):
                        chunks = [chunk async for chunk in llm_service.stream_chat(
                            messages, enable_thinking=enabled,
                        )]
                    self.assertEqual(chunks, ["范围说明"])
                    self.assertEqual(router.ainvoke.await_args.kwargs["extra_body"], {"enable_thinking": enabled})
                    self.assertEqual(model.ainvoke.await_args.kwargs["extra_body"], {"enable_thinking": enabled})

    async def test_scope_response_failure_uses_reason_specific_fallback(self):
        for reason in workflow.OUT_OF_SCOPE_FALLBACKS:
            with self.subTest(reason=reason):
                self.reply.side_effect = TimeoutError()
                result = await workflow.respond_out_of_scope({
                    "messages": [HumanMessage(content="请求")],
                    "out_of_scope_reason": reason,
                })
                self.assertEqual(result["response"], workflow.OUT_OF_SCOPE_FALLBACKS[reason])

    async def test_empty_or_excessive_scope_response_falls_back(self):
        for reply in ("   ", None, "文" * 301):
            self.reply.return_value = reply
            result = await workflow.respond_out_of_scope({"messages": [HumanMessage(content="请求")]})
            self.assertEqual(result["response"], workflow.OUT_OF_SCOPE_FALLBACKS["unrelated"])

    async def test_reason_reaches_response_but_internal_route_reason_does_not(self):
        with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
            classify.return_value = RouteDecision(
                intent="out_of_scope", out_of_scope_reason="permission_restricted",
                route_reason="内部分类依据",
            )
            await workflow.run([HumanMessage(content="替我审批预约")])
        messages = self.reply.await_args.args[0]
        self.assertIn("permission_restricted", messages[0].content)
        self.assertNotIn("内部分类依据", messages[0].content)
        self.assertEqual(messages[-1].content, "替我审批预约")

    async def test_supported_intent_skips_response_generation(self):
        with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
            classify.return_value = RouteDecision(intent="resource_query", route_reason="查设备")
            await workflow.run([HumanMessage(content="有哪些设备")])
        self.reply.assert_not_awaited()

    async def test_resource_query_calls_laboratory_workflow(self):
        with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
            classify.return_value = RouteDecision(intent="resource_query", route_reason="查实验室")
            with patch.object(workflow.laboratory, "run", new_callable=AsyncMock) as run_laboratory:
                run_laboratory.return_value = "开放实验室：A101"
                response = await workflow.run(
                    [HumanMessage(content="有哪些实验室")], db=object(), user_role="admin"
                )
        self.assertEqual(response, "开放实验室：A101")
        self.assertEqual(run_laboratory.await_args.kwargs["user_role"], "admin")

    async def test_pending_intent_generates_contextual_reply(self):
        self.reply.return_value = "这个功能还没开放，不过我可以帮你查实验室和设备。"
        with patch.object(llm_service, "classify_request", new_callable=AsyncMock) as classify:
            classify.return_value = RouteDecision(intent="availability_query", route_reason="查空闲")
            result = await workflow.run([HumanMessage(content="明天下午有空的实验室吗？")])
        self.assertEqual(result, self.reply.return_value)
        self.assertEqual(self.reply.await_args.args[0][-1].content, "明天下午有空的实验室吗？")

    async def test_invalid_scope_reason_rejected(self):
        with self.assertRaises(ValidationError):
            RouteDecision(intent="out_of_scope", route_reason="测试", out_of_scope_reason="other")


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
        query = LaboratoryQuery(target="equipment", equipment_keyword="电子显微镜")
        with patch.object(llm_service, "plan_laboratory_query", return_value=query):
            with patch.object(llm_service, "generate_scope_response", side_effect=TimeoutError):
                reply = await laboratory.run(messages, db=self.db)
        self.assertIn("EQ-1）", reply)
        self.assertIn("在[纳米实验室](#resource-match)（A楼）", reply)
        self.assertIn("维修，在[光学实验室](#resource-match)（B楼）", reply)
        self.assertNotIn("光谱仪", reply)

    async def test_followup_sends_context_and_uses_device_code(self):
        messages = [
            HumanMessage(content="EQ-2 在哪个实验室？"),
            AIMessage(content="在光学实验室。"),
            HumanMessage(content="哪栋楼？"),
        ]
        query = LaboratoryQuery(target="equipment", equipment_keyword="EQ-2")
        with patch.object(llm_service, "classify_request", return_value=RouteDecision(
            intent="resource_query", route_reason="追问设备位置",
        )):
            with patch.object(llm_service, "plan_laboratory_query", return_value=query) as plan:
                with patch.object(llm_service, "generate_scope_response", return_value="在 B 楼。") as answer:
                    reply = await workflow.run(messages, db=self.db)
        self.assertEqual(reply, "在 B 楼。")
        self.assertEqual(plan.await_args.args[0][1:], messages)
        facts = answer.await_args.args[0][-1].content
        self.assertIn("B楼", facts)
        self.assertNotIn("A楼", facts)

    async def test_lab_keyword_and_equipment_keyword_are_both_applied(self):
        query = LaboratoryQuery(
            target="equipment", lab_keyword="LAB-1", equipment_keyword="光谱仪",
        )
        result, fallback = await laboratory._lookup(self.db, query)
        self.assertEqual(result["total"], 0)
        self.assertIn("没查到", fallback)

    async def test_lab_lookup_can_return_closed_lab_details(self):
        query = LaboratoryQuery(target="laboratory", lab_keyword="光学实验室")
        result, _ = await laboratory._lookup(self.db, query)
        self.assertEqual(result["laboratories"][0]["location"], "B楼")
        self.assertEqual(result["laboratories"][0]["status"], "关闭")

    async def test_device_search_can_filter_by_lab_status(self):
        query = LaboratoryQuery(
            target="equipment", equipment_keyword="显微镜", lab_status="closed",
        )
        result, _ = await laboratory._lookup(self.db, query)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["equipment"][0]["code"], "EQ-2")

    async def test_full_lab_list_keeps_requested_columns_and_bypasses_page_limit(self):
        self.db.add_all([
            Lab(
                name=f"测试实验室{number}", lab_code=f"LIST-{number:02}",
                capacity=number, open_time=time(8, 30), close_time=time(17, 30),
            )
            for number in range(1, 20)
        ])
        await self.db.commit()
        messages = [HumanMessage(content="用列表的形式列出来所有的实验室名称，容量，开放时间")]
        query = LaboratoryQuery(
            target="laboratory", lab_status="open",
            lab_fields=["name", "capacity", "opening_hours"],
        )
        with patch.object(llm_service, "plan_laboratory_query", return_value=query):
            with patch.object(llm_service, "generate_scope_response") as generate:
                reply = await laboratory.run(messages, db=self.db)
        generate.assert_not_awaited()
        lines = reply.splitlines()
        self.assertEqual(lines[:2], ["| 实验室名称 | 容量 | 开放时间 |", "| --- | --- | --- |"])
        self.assertEqual(len(lines[2:]), 21)
        self.assertIn("| [测试实验室19](#resource-match) | 19 人 | 08:30–17:30 |", lines)
        self.assertIn("| [光学实验室](#resource-match) | 0 人 | 未登记 |", lines)
        self.assertTrue(all(line.startswith("| ") for line in lines[2:]))
