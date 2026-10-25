from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    model_mode: Literal["demo", "openai-compatible"] = "demo"
    model_name: str = "gpt-4.1-mini"
    model_base_url: str | None = None
    model_api_key: str | None = None
    model_temperature: float = 0.0

    checkpointer: Literal["memory"] = "memory"
    sqlite_path: Path = Path("data/runtime/checkpoints.sqlite")

    knowledge_dir: Path = Path("knowledge")
    mock_telemetry_path: Path = Path("data/mock_telemetry.json")
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    min_evidence_score: float = Field(default=0.08, ge=0.0, le=1.0)
    human_review_risk_level: Literal["medium", "high", "critical"] = "high"
    alarm_webhook_token: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
