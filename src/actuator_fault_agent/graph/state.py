from typing import Any, TypedDict


class DiagnosisState(TypedDict, total=False):
    thread_id: str
    trigger_source: str
    event_id: str | None
    alarm_source_system: str | None
    alarm_severity: str | None
    alarm_occurred_at: str | None
    alarm_metadata: dict[str, Any]
    question: str
    actuator_id: str
    station: str
    product_model: str | None
    fault_code: str | None
    supplied_measurements: dict[str, Any] | None
    require_human_review: bool

    normalized_query: str
    diagnostic_query: str
    measurements: dict[str, Any] | None
    baseline_evidence: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    rule_findings: list[dict[str, Any]]
    diagnosis: dict[str, Any] | None
    review_required: bool
    review_reason: str | None
    review_decision: dict[str, Any] | None
    status: str
