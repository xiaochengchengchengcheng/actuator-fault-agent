from typing import Any

from actuator_fault_agent.config import Settings


def create_chat_model(settings: Settings) -> Any | None:
    if settings.model_mode == "demo":
        return None

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.model_name,
        base_url=settings.model_base_url,
        api_key=settings.model_api_key,
        temperature=settings.model_temperature,
        max_retries=2,
        timeout=60,
    )
