from langchain_openai import ChatOpenAI

from core.config import settings


def create_llm() -> ChatOpenAI:
    """
    创建统一的大模型实例。

    目前使用 OpenAI 兼容接口，
    可以通过配置切换不同模型服务商。
    """
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        timeout=settings.LLM_TIMEOUT,
        max_retries=settings.LLM_MAX_RETRIES,
        streaming=True,
    )
