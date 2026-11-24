"""Laboratory workflow orchestration."""
from services.workflows.laboratory.agents import laboratory_agent


async def run(messages, *, db, enable_thinking=False):
    return await laboratory_agent.run(messages, db=db, enable_thinking=enable_thinking)
