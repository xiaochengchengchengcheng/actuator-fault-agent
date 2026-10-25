from dataclasses import dataclass
from typing import Any

from actuator_fault_agent.domain.models import AlarmEvent, TriggerSource


@dataclass(frozen=True)
class AlarmIngestionSkill:
    """Translate a production alarm event into the graph's stable input contract."""

    def build_graph_input(self, event: AlarmEvent, thread_id: str) -> dict[str, Any]:
        question = (
            f"产线故障检测装置上报报警 {event.alarm_code}：{event.alarm_message}。"
            "请结合当前实时数据、受控知识和安全规则生成诊断报告。"
        )
        return {
            "thread_id": thread_id,
            "trigger_source": TriggerSource.ALARM.value,
            "event_id": event.event_id,
            "alarm_source_system": event.source_system,
            "alarm_severity": event.severity.value,
            "alarm_occurred_at": event.occurred_at.isoformat(),
            "alarm_metadata": event.metadata,
            "question": question,
            "actuator_id": event.actuator_id,
            "station": event.station,
            "product_model": event.product_model,
            "fault_code": event.alarm_code,
            "supplied_measurements": event.measurements,
            "require_human_review": False,
        }
