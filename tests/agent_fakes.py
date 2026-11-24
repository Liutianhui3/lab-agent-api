"""Scripted tool-capable model used with the real create_agent loop."""
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class ToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def call(name, args=None, identity="call-1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": identity}])


def model(*messages):
    return ToolModel(messages=iter(messages))
