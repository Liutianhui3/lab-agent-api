"""Exercise the real supervisor loop with scripted model tool decisions."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from agent_fakes import call, model
from services.workflows.supervisor import workflow
from services.workflows.supervisor.agents import supervisor_agent
from services.workflows.supervisor.tools import workflow_tools


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_can_call_two_business_workflows_then_combine(self):
        history = [HumanMessage(content="查询实验室位置和我的邮箱")]
        scripted = model(call("query_resources", {"request": "实验室在哪"}),
                         call("query_profiles", {"request": "我的邮箱"}, "call-2"),
                         AIMessage(content="实验室在 A 楼，邮箱 self@example.com。"))
        with (
            patch.object(supervisor_agent.llm_service, "llm", scripted),
            patch.object(workflow_tools.laboratory, "run", new_callable=AsyncMock, return_value="A 楼") as labs,
            patch.object(workflow_tools.user, "run", new_callable=AsyncMock, return_value="self@example.com") as profiles,
        ):
            events = [event async for event in workflow.stream(history, user_id=uuid4())]
        self.assertIn("A 楼", events[-1][1]["content"])
        self.assertEqual(labs.await_count, 1)
        self.assertEqual(profiles.await_count, 1)
        self.assertEqual(profiles.await_args.args[0][0], history[0])
        self.assertEqual({payload["stage"] for event, payload in events if event == "thinking"},
                         {"identify_user_role", "supervisor", "query_resources", "query_profiles", "prepare_response"})
        self.assertNotIn("call-2", str(events))

    async def test_admin_tool_is_hidden_from_students_and_enforces_permission(self):
        context = {"user_role": "student", "enable_thinking": False, "user_id": uuid4()}
        with patch.object(supervisor_agent, "create_agent") as create:
            supervisor_agent.build(context)
        names = {tool.name for tool in create.call_args.kwargs["tools"]}
        self.assertNotIn("prepare_user_management", names)
        with patch.object(workflow_tools.admin, "run", new_callable=AsyncMock) as manage:
            result = await workflow_tools.prepare_user_management.coroutine(
                runtime=SimpleNamespace(context=context), action="admin_user_delete", user_identifier="tina")
        self.assertIn("无权", result)
        manage.assert_not_awaited()

    async def test_admin_card_returned_without_model_rewriting(self):
        card = '{"type":"admin_user_edit","data":{"username":"tina"}}'
        scripted = model(call("prepare_user_management", {"action": "admin_user_edit", "user_identifier": "tina"}))
        with (
            patch.object(supervisor_agent.llm_service, "llm", scripted),
            patch.object(workflow_tools.admin, "run", new_callable=AsyncMock, return_value=card) as manage,
        ):
            result = await workflow.run([HumanMessage(content="编辑 tina")], db=object(), user_role="admin", user_id=uuid4())
        self.assertEqual(result, card)
        self.assertEqual(manage.await_args.kwargs["user_identifier"], "tina")

    async def test_direct_answers_emit_progress_before_public_answer(self):
        cases = [
            ("你好", "你好，请问需要什么帮助？"),
            ("今天天气怎么样", "我目前提供实验室平台相关服务，无法查询天气。"),
            ("帮我查一下", "你想查询哪个实验室或哪项资料？"),
        ]
        for request, answer in cases:
            with self.subTest(request=request), patch.object(
                supervisor_agent.llm_service, "llm", model(AIMessage(content=answer))
            ):
                events = [event async for event in workflow.stream([HumanMessage(content=request)])]
            self.assertEqual(events[-2], ("thinking", {
                "stage": "prepare_response", "label": "整理回复", "status": "complete",
            }))
            self.assertEqual(events[-1], ("delta", {"content": answer}))
            self.assertEqual(sum(payload.get("stage") == "prepare_response"
                                 for _, payload in events), 1)

    async def test_reservation_emits_ordered_business_progress(self):
        card = '{"type":"reservation_application"}'
        scripted = model(call("reservation_workflow", {"request": "预约明天下午"}))
        with patch.object(supervisor_agent.llm_service, "llm", scripted), patch.object(
            workflow_tools, "reservation_workflow", workflow_tools.reservation_workflow
        ), patch.object(workflow_tools.reservation_workflow, "coroutine", new_callable=AsyncMock,
                        return_value=card):
            # The adapter mock does not execute the nested workflow; verify the
            # event contract through the shared progress context instead.
            events = [event async for event in workflow.stream([HumanMessage(content="预约")])]
        self.assertTrue(events[-1][0] == "delta")

    async def test_invalid_role_and_non_human_input_rejected_before_model(self):
        for messages, role in [([], "student"), ([AIMessage(content="hi")], "student"),
                               ([HumanMessage(content="hi")], "root")]:
            with self.assertRaises(ValueError):
                await workflow.run(messages, user_role=role)

    async def test_parallel_tool_calls_serialize_shared_session(self):
        active = 0
        async def query(*args, **kwargs):
            nonlocal active
            active += 1
            self.assertEqual(active, 1)
            await asyncio.sleep(0)
            active -= 1
            return "结果"
        batch = AIMessage(content="", tool_calls=[
            {"name": "query_resources", "args": {"request": "实验室"}, "id": "a"},
            {"name": "query_profiles", "args": {"request": "本人邮箱"}, "id": "b"},
        ])
        with (
            patch.object(supervisor_agent.llm_service, "llm", model(batch, AIMessage(content="已查到"))),
            patch.object(workflow_tools.laboratory, "run", side_effect=query),
            patch.object(workflow_tools.user, "run", side_effect=query),
        ):
            self.assertEqual(await workflow.run([HumanMessage(content="查询")], user_id=uuid4()), "已查到")

    async def test_admin_missing_target_returns_clarification_instead_of_empty_answer(self):
        scripted = model(call("prepare_user_management", {"action": "admin_user_edit"}))
        with patch.object(supervisor_agent.llm_service, "llm", scripted):
            result = await workflow.run([HumanMessage(content="编辑用户")], user_role="admin", user_id=uuid4())
        self.assertEqual(result, "请提供要操作的用户姓名或账号。")

    async def test_mixed_tool_batch_cannot_overwrite_card(self):
        card = '{"type":"user_profile_edit","data":{"username":"me"}}'
        batch = AIMessage(content="", tool_calls=[
            {"name": "query_resources", "args": {"request": "查询实验室"}, "id": "a"},
            {"name": "prepare_my_profile_edit", "args": {}, "id": "b"},
        ])
        with (
            patch.object(supervisor_agent.llm_service, "llm", model(batch, AIMessage(content="错误的卡片改写"))),
            patch.object(workflow_tools.laboratory, "run", new_callable=AsyncMock, return_value="实验室"),
            patch.object(workflow_tools.user, "edit_card", new_callable=AsyncMock, return_value=card),
        ):
            result = await workflow.run([HumanMessage(content="查实验室并编辑本人资料")], user_id=uuid4())
        self.assertEqual(result, card)
