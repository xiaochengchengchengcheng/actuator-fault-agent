import hmac
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from langgraph.types import Command

from actuator_fault_agent.config import get_settings
from actuator_fault_agent.domain.models import (
    AlarmEvent,
    DiagnosisRequest,
    DiagnosisResponse,
    ReviewDecision,
    TriggerSource,
)
from actuator_fault_agent.graph.builder import graph
from actuator_fault_agent.skills import AlarmIngestionSkill

app = FastAPI(
    title="Actuator Fault Diagnosis Agent",
    version="0.1.0",
    description="Evidence-grounded diagnosis API for electromechanical actuator production.",
)
settings = get_settings()
alarm_skill = AlarmIngestionSkill()


def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupts = result.get("__interrupt__", ())
    if not interrupts:
        return None
    first = interrupts[0]
    return first.value if hasattr(first, "value") else dict(first)


def _response(thread_id: str, result: dict[str, Any]) -> DiagnosisResponse:
    review_payload = _interrupt_payload(result)
    if review_payload is not None:
        return DiagnosisResponse(
            thread_id=thread_id,
            status="review_required",
            trigger_source=result.get("trigger_source", TriggerSource.ENGINEER),
            event_id=result.get("event_id"),
            diagnostic_query=result.get("diagnostic_query"),
            measurements=result.get("measurements"),
            evidence=result.get("evidence", []),
            diagnosis=result.get("diagnosis"),
            review_payload=review_payload,
        )
    status = result.get("status", "insufficient_evidence")
    return DiagnosisResponse(
        thread_id=thread_id,
        status=status,
        trigger_source=result.get("trigger_source", TriggerSource.ENGINEER),
        event_id=result.get("event_id"),
        diagnostic_query=result.get("diagnostic_query"),
        measurements=result.get("measurements"),
        evidence=result.get("evidence", []),
        diagnosis=result.get("diagnosis"),
    )


def _run(initial: dict[str, Any], thread_id: str) -> DiagnosisResponse:
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial, config=config)
    return _response(thread_id, result)


def _verify_alarm_token(received: str | None) -> None:
    configured = settings.alarm_webhook_token
    expected = configured.get_secret_value() if configured else ""
    if expected and (received is None or not hmac.compare_digest(expected, received)):
        raise HTTPException(status_code=401, detail="Invalid alarm webhook token")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/diagnoses", response_model=DiagnosisResponse)
def diagnose(request: DiagnosisRequest) -> DiagnosisResponse:
    thread_id = str(uuid4())
    initial = {
        "thread_id": thread_id,
        "trigger_source": TriggerSource.ENGINEER.value,
        "event_id": None,
        "question": request.question,
        "actuator_id": request.actuator_id,
        "station": request.station,
        "product_model": request.product_model,
        "fault_code": request.fault_code,
        "supplied_measurements": request.measurements,
        "require_human_review": request.require_human_review,
    }
    return _run(initial, thread_id)


@app.post("/v1/alarms/events", response_model=DiagnosisResponse)
def receive_alarm(
    event: AlarmEvent,
    x_alarm_token: str | None = Header(default=None, alias="X-Alarm-Token"),
) -> DiagnosisResponse:
    """Receive one alarm event and run the same evidence-grounded diagnosis graph."""
    _verify_alarm_token(x_alarm_token)
    thread_id = str(uuid4())
    initial = alarm_skill.build_graph_input(event, thread_id)
    return _run(initial, thread_id)


@app.post("/v1/diagnoses/{thread_id}/resume", response_model=DiagnosisResponse)
def resume_diagnosis(thread_id: str, decision: ReviewDecision) -> DiagnosisResponse:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = graph.invoke(Command(resume=decision.model_dump(mode="json")), config=config)
    except Exception as exc:
        raise HTTPException(
            status_code=409, detail="No resumable diagnosis found for thread"
        ) from exc
    return _response(thread_id, result)
