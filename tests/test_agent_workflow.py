"""不调用真实模型，验证图分支、结构化校验和 SSE 输出边界。"""

import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from schemas.agent import RouteDecision
from services.agent import workflow
from services.llm import llm_service


class AgentWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
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
                    self.assertEqual(result, workflow.PENDING_RESPONSE)

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

    async def test_invalid_scope_reason_rejected(self):
        with self.assertRaises(ValidationError):
            RouteDecision(intent="out_of_scope", route_reason="测试", out_of_scope_reason="other")
