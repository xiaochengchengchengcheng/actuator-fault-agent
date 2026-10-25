from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from actuator_fault_agent.config import Settings, get_settings
from actuator_fault_agent.domain.models import RiskLevel
from actuator_fault_agent.graph.nodes import (
    build_diagnostic_query,
    end_rejected,
    finalize,
    human_review,
    make_baseline_retrieve_node,
    make_diagnostic_retrieve_node,
    make_measurement_node,
    make_risk_gate,
    make_synthesis_node,
    route_after_gate,
    rule_screening,
    validate_input,
)
from actuator_fault_agent.graph.state import DiagnosisState
from actuator_fault_agent.retrieval.knowledge_base import LocalKnowledgeBase
from actuator_fault_agent.services.llm import create_chat_model
from actuator_fault_agent.services.telemetry import JsonTelemetryRepository
from actuator_fault_agent.services.tools import build_read_tools


@dataclass
class GraphServices:
    settings: Settings
    knowledge_base: LocalKnowledgeBase
    telemetry_repository: JsonTelemetryRepository
    model: Any | None


def create_services(settings: Settings | None = None) -> GraphServices:
    current = settings or get_settings()
    return GraphServices(
        settings=current,
        knowledge_base=LocalKnowledgeBase(current.knowledge_dir),
        telemetry_repository=JsonTelemetryRepository(current.mock_telemetry_path),
        model=create_chat_model(current),
    )


def build_graph(services: GraphServices | None = None):
    services = services or create_services()
    tools = build_read_tools(services.telemetry_repository)

    builder = StateGraph(DiagnosisState)
    builder.add_node("validate_input", validate_input)
    builder.add_node(
        "retrieve_baseline_knowledge",
        make_baseline_retrieve_node(
            services.knowledge_base,
            services.settings.retrieval_top_k,
            services.settings.min_evidence_score,
        ),
    )
    builder.add_node(
        "load_measurements",
        make_measurement_node(tools["get_latest_measurements"]),
    )
    builder.add_node("rule_screening", rule_screening)
    builder.add_node("build_diagnostic_query", build_diagnostic_query)
    builder.add_node(
        "retrieve_diagnostic_knowledge",
        make_diagnostic_retrieve_node(
            services.knowledge_base,
            services.settings.retrieval_top_k,
            services.settings.min_evidence_score,
        ),
    )
    builder.add_node("synthesize", make_synthesis_node(services.model))
    builder.add_node(
        "risk_gate",
        make_risk_gate(RiskLevel(services.settings.human_review_risk_level)),
    )
    builder.add_node("human_review", human_review)
    builder.add_node("finalize", finalize)
    builder.add_node("end_rejected", end_rejected)

    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "retrieve_baseline_knowledge")
    builder.add_edge("retrieve_baseline_knowledge", "load_measurements")
    builder.add_edge("load_measurements", "rule_screening")
    builder.add_edge("rule_screening", "build_diagnostic_query")
    builder.add_edge("build_diagnostic_query", "retrieve_diagnostic_knowledge")
    builder.add_edge("retrieve_diagnostic_knowledge", "synthesize")
    builder.add_edge("synthesize", "risk_gate")
    builder.add_conditional_edges(
        "risk_gate",
        route_after_gate,
        {"human_review": "human_review", "finalize": "finalize"},
    )
    builder.add_edge("finalize", END)
    builder.add_edge("end_rejected", END)
    return builder.compile(checkpointer=InMemorySaver())


# LangGraph CLI/Studio entrypoint.
graph = build_graph()
