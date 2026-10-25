import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt

from actuator_fault_agent.domain.models import (
    CandidateCause,
    DiagnosisDraft,
    Evidence,
    MeasurementSnapshot,
    ReviewDecision,
    RiskLevel,
    RuleFinding,
)
from actuator_fault_agent.domain.rules import highest_risk, screen_measurements
from actuator_fault_agent.graph.state import DiagnosisState
from actuator_fault_agent.retrieval.knowledge_base import LocalKnowledgeBase

RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def validate_input(state: DiagnosisState) -> dict[str, Any]:
    parts = [state["question"], state["actuator_id"], state["station"]]
    if state.get("product_model"):
        parts.append(str(state["product_model"]))
    if state.get("fault_code"):
        parts.append(str(state["fault_code"]))
    return {"normalized_query": " ".join(parts), "status": "running"}


def make_baseline_retrieve_node(
    knowledge_base: LocalKnowledgeBase, top_k: int, min_score: float
) -> Callable:
    def retrieve_baseline_knowledge(state: DiagnosisState) -> dict[str, Any]:
        evidence = [
            item
            for item in knowledge_base.search(state["normalized_query"], top_k=top_k)
            if item.score >= min_score
        ]
        return {"baseline_evidence": [item.model_dump(mode="json") for item in evidence]}

    return retrieve_baseline_knowledge


def make_measurement_node(read_tool: Any) -> Callable:
    def load_measurements(state: DiagnosisState) -> dict[str, Any]:
        supplied = state.get("supplied_measurements")
        if supplied:
            snapshot = MeasurementSnapshot(
                actuator_id=state["actuator_id"],
                station=state["station"],
                values=supplied,
                source="request",
            )
            return {"measurements": snapshot.model_dump(mode="json")}
        result = read_tool.invoke(
            {"actuator_id": state["actuator_id"], "station": state["station"]}
        )
        if result.get("status") == "not_found":
            return {"measurements": None}
        return {"measurements": result}

    return load_measurements


def rule_screening(state: DiagnosisState) -> dict[str, Any]:
    raw = state.get("measurements")
    if not raw:
        return {"rule_findings": []}
    snapshot = MeasurementSnapshot.model_validate(raw)
    findings = screen_measurements(snapshot)
    return {"rule_findings": [finding.model_dump(mode="json") for finding in findings]}


def build_diagnostic_query(state: DiagnosisState) -> dict[str, Any]:
    parts = [state["question"]]
    if state.get("fault_code"):
        parts.append(f"故障码: {state['fault_code']}")
    if state.get("product_model"):
        parts.append(f"产品型号: {state['product_model']}")
    parts.append(f"工位: {state['station']}")

    findings = [RuleFinding.model_validate(item) for item in state.get("rule_findings", [])]
    if findings:
        anomaly_text = "；".join(
            f"{finding.title}（{finding.observation}）" for finding in findings
        )
        parts.append(f"异常特征: {anomaly_text}")

    raw_measurements = state.get("measurements")
    if raw_measurements:
        snapshot = MeasurementSnapshot.model_validate(raw_measurements)
        values = "，".join(f"{key}={value}" for key, value in snapshot.values.items())
        parts.append(f"实时数据: {values}")
    else:
        parts.append("实时数据: 未获取")

    return {"diagnostic_query": "\n".join(parts)}


def make_diagnostic_retrieve_node(
    knowledge_base: LocalKnowledgeBase, top_k: int, min_score: float
) -> Callable:
    def retrieve_diagnostic_knowledge(state: DiagnosisState) -> dict[str, Any]:
        diagnostic = [
            item
            for item in knowledge_base.search(state["diagnostic_query"], top_k=top_k)
            if item.score >= min_score
        ]
        combined: list[Evidence] = diagnostic[:]
        known_ids = {item.evidence_id for item in combined}
        for raw in state.get("baseline_evidence", []):
            item = Evidence.model_validate(raw)
            if item.evidence_id not in known_ids:
                combined.append(item)
                known_ids.add(item.evidence_id)
        return {"evidence": [item.model_dump(mode="json") for item in combined[: top_k * 2]]}

    return retrieve_diagnostic_knowledge


def _fallback_diagnosis(state: DiagnosisState) -> DiagnosisDraft:
    findings = [RuleFinding.model_validate(item) for item in state.get("rule_findings", [])]
    evidence = [Evidence.model_validate(item) for item in state.get("evidence", [])]
    evidence_ids = [item.evidence_id for item in evidence[:3]]
    candidates: list[CandidateCause] = []
    for finding in findings[:5]:
        cause = finding.possible_causes[0] if finding.possible_causes else finding.title
        candidates.append(
            CandidateCause(
                cause=cause,
                confidence=0.72 if evidence_ids else 0.52,
                rationale=finding.observation,
                evidence_ids=evidence_ids
                or [f"measurement:{key}" for key in finding.evidence_keys],
                verification_steps=finding.verification_steps,
            )
        )
    if not candidates and evidence:
        candidates.append(
            CandidateCause(
                cause="现有信息只能形成初步方向，尚不能确认根因",
                confidence=0.35,
                rationale="知识检索有命中，但测量数据未触发受控规则。",
                evidence_ids=evidence_ids,
                verification_steps=[
                    "补充完整 EOL 测量结果",
                    "核对产品型号和工艺版本",
                    "复现故障并记录波形",
                ],
            )
        )
    risk = highest_risk(findings)
    alarm_severity = state.get("alarm_severity")
    if alarm_severity:
        alarm_risk = RiskLevel(alarm_severity)
        if RISK_RANK[alarm_risk] > RISK_RANK[risk]:
            risk = alarm_risk
    missing = []
    if not state.get("measurements"):
        missing.append("当前工位测量快照")
    if not evidence:
        missing.append("与型号和故障现象匹配的受控知识")
    return DiagnosisDraft(
        summary="检测到可疑生产故障，建议按证据优先级逐项验证。"
        if candidates
        else "证据不足，暂不能形成可靠诊断。",
        risk_level=risk,
        likely_causes=candidates,
        immediate_actions=[
            "隔离疑似不合格品并保留原始测试记录",
            "先验证测试夹具和测量系统，再拆检产品",
        ],
        missing_data=missing,
        safety_notes=["涉及绝缘、耐压、过温或重新通电时，必须执行现场安全规程。"]
        if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        else [],
        evidence_sufficient=bool(candidates and (findings or evidence)),
    )


def make_synthesis_node(model: Any | None) -> Callable:
    def synthesize(state: DiagnosisState) -> dict[str, Any]:
        if model is None:
            draft = _fallback_diagnosis(state)
            return {"diagnosis": draft.model_dump(mode="json")}

        structured_model = model.with_structured_output(DiagnosisDraft)
        evidence = state.get("evidence", [])
        findings = state.get("rule_findings", [])
        prompt = {
            "trigger_source": state.get("trigger_source", "engineer"),
            "event_id": state.get("event_id"),
            "alarm_source_system": state.get("alarm_source_system"),
            "alarm_severity": state.get("alarm_severity"),
            "alarm_occurred_at": state.get("alarm_occurred_at"),
            "question": state["question"],
            "actuator_id": state["actuator_id"],
            "station": state["station"],
            "product_model": state.get("product_model"),
            "fault_code": state.get("fault_code"),
            "measurements": state.get("measurements"),
            "rule_findings": findings,
            "diagnostic_query": state.get("diagnostic_query"),
            "knowledge_evidence": evidence,
        }
        system = (
            "你是机电执行器制造质量诊断助手。只依据输入中的测量、规则命中和知识证据作答。"
            "每个候选原因必须引用 evidence_id 或 measurement:key；不能虚构阈值、型号、工艺参数或已执行的动作。"
            "把假设写成待验证候选原因，给出可执行的验证顺序。电气安全失败、过温和高振动必须提高风险等级。"
            "证据不足时 evidence_sufficient=false，并明确 missing_data。不要输出设备控制指令。"
        )
        try:
            draft = structured_model.invoke(
                [
                    SystemMessage(content=system),
                    HumanMessage(content=json.dumps(prompt, ensure_ascii=False)),
                ]
            )
        except Exception:
            draft = _fallback_diagnosis(state)
        alarm_severity = state.get("alarm_severity")
        if alarm_severity:
            alarm_risk = RiskLevel(alarm_severity)
            if RISK_RANK[alarm_risk] > RISK_RANK[draft.risk_level]:
                draft.risk_level = alarm_risk
        return {"diagnosis": draft.model_dump(mode="json")}

    return synthesize


def make_risk_gate(review_threshold: RiskLevel) -> Callable:
    def risk_gate(state: DiagnosisState) -> dict[str, Any]:
        diagnosis = DiagnosisDraft.model_validate(state["diagnosis"])
        needs_review = state.get("require_human_review", False)
        reasons: list[str] = []
        if RISK_RANK[diagnosis.risk_level] >= RISK_RANK[review_threshold]:
            needs_review = True
            reasons.append(f"风险等级为 {diagnosis.risk_level.value}")
        if not diagnosis.evidence_sufficient:
            needs_review = True
            reasons.append("诊断证据不足")
        if any(
            RuleFinding.model_validate(item).code == "ELECTRICAL_SAFETY_FAIL"
            for item in state.get("rule_findings", [])
        ):
            needs_review = True
            reasons.append("电气安全测试失败")
        if state.get("alarm_severity") == RiskLevel.CRITICAL.value:
            needs_review = True
            reasons.append("报警装置上报 critical 级事件")
        return {
            "review_required": needs_review,
            "review_reason": "；".join(reasons) if reasons else None,
        }

    return risk_gate


def route_after_gate(state: DiagnosisState) -> str:
    return "human_review" if state.get("review_required") else "finalize"


def human_review(state: DiagnosisState) -> Command:
    decision_payload = interrupt(
        {
            "type": "diagnosis_review",
            "reason": state.get("review_reason"),
            "actuator_id": state["actuator_id"],
            "station": state["station"],
            "trigger_source": state.get("trigger_source", "engineer"),
            "event_id": state.get("event_id"),
            "diagnosis": state.get("diagnosis"),
            "instruction": "请由授权的质量或工艺人员批准、拒绝或编辑处置建议。",
        }
    )
    decision = ReviewDecision.model_validate(decision_payload)
    diagnosis = DiagnosisDraft.model_validate(state["diagnosis"])
    if decision.edited_immediate_actions is not None:
        diagnosis.immediate_actions = decision.edited_immediate_actions
    return Command(
        update={
            "review_decision": decision.model_dump(mode="json"),
            "diagnosis": diagnosis.model_dump(mode="json"),
            "status": "running" if decision.approved else "rejected",
        },
        goto="finalize" if decision.approved else "end_rejected",
    )


def finalize(state: DiagnosisState) -> dict[str, Any]:
    diagnosis = DiagnosisDraft.model_validate(state["diagnosis"])
    status = "completed" if diagnosis.evidence_sufficient else "insufficient_evidence"
    return {"status": status}


def end_rejected(state: DiagnosisState) -> dict[str, Any]:
    return {"status": "rejected"}
