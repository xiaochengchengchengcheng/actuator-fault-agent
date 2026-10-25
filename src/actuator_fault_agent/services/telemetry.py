import json
from pathlib import Path
from typing import Protocol

from actuator_fault_agent.domain.models import MeasurementSnapshot


class TelemetryRepository(Protocol):
    def get_latest(self, actuator_id: str, station: str) -> MeasurementSnapshot | None: ...


class JsonTelemetryRepository:
    def __init__(self, path: Path):
        self.path = path

    def get_latest(self, actuator_id: str, station: str) -> MeasurementSnapshot | None:
        if not self.path.exists():
            return None
        records = json.loads(self.path.read_text(encoding="utf-8"))
        for record in records:
            if record["actuator_id"] == actuator_id and record["station"] == station:
                return MeasurementSnapshot.model_validate(record)
        return None
