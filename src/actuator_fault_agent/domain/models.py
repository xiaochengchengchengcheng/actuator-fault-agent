from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TriggerSource(StrEnum):
    ENGINEER = "engineer"
    ALARM = "alarm"


class DiagnosisRequest(BaseModel):
    question: str = Field(min_length=4, max_length=2000)
    actuator_id: str = Field(min_length=2, max_length=80)
    station: str = Field(min_length=2, max_length=80)
    product_model: str | None = Field(default=None, max_length=80)
    fault_code: str | None = Field(default=None, max_length=80)
    measurements: dict[str, float | int | str | bool | None] | None = None
    require_human_review: bool = False


class AlarmEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=120)
    source_system: str = Field(min_length=1, max_length=120)
    actuator_id: str = Field(min_length=2, max_length=80)
    station: str = Field(min_length=2, max_length=80)
    alarm_code: str = Field(min_length=1, max_length=80)
    alarm_message: str = Field(min_length=2, max_length=1000)
    severity: RiskLevel = RiskLevel.MEDIUM
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    product_model: str | None = Field(default=None, max_length=80)
    measurements: dict[str, float | int | str | bool | None] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MeasurementSnapshot(BaseModel):
    actuator_id: str
    station: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    values: dict[str, float | int | str | bool | None]
    source: str = "unknown"
    quality: Literal["good", "suspect", "bad"] = "good"


class Evidence(BaseModel):
    evidence_id: str
    title: str
    content: str
    source: str
    locator: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleFinding(BaseModel):
    code: str
    title: str
    risk: RiskLevel
    observation: str
    possible_causes: list[str]
    verification_steps: list[str]
    evidence_keys: list[str] = Field(default_factory=list)


class CandidateCause(BaseModel):
    cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)


class DiagnosisDraft(BaseModel):
    summary: str
    risk_level: RiskLevel
    likely_causes: list[CandidateCause] = Field(default_factory=list, max_length=5)
    immediate_actions: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    evidence_sufficient: bool = False

    @model_validator(mode="after")
    def require_grounding(self) -> "DiagnosisDraft":
        for cause in self.likely_causes:
            if not cause.evidence_ids:
                raise ValueError(f"Candidate cause has no evidence: {cause.cause}")
        return self


class ReviewDecision(BaseModel):
    approved: bool
    reviewer: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=1000)
    edited_immediate_actions: list[str] | None = None


class DiagnosisResponse(BaseModel):
    thread_id: str
    status: Literal["completed", "review_required", "rejected", "insufficient_evidence"]
    trigger_source: TriggerSource = TriggerSource.ENGINEER
    event_id: str | None = None
    diagnostic_query: str | None = None
    measurements: MeasurementSnapshot | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    diagnosis: DiagnosisDraft | None = None
    review_payload: dict[str, Any] | None = None
