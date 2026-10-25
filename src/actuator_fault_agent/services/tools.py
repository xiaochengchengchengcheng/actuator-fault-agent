from langchain.tools import tool

from actuator_fault_agent.services.telemetry import TelemetryRepository


def build_read_tools(repository: TelemetryRepository):
    @tool
    def get_latest_measurements(actuator_id: str, station: str) -> dict:
        """Read the latest measurements for one actuator at one production station."""
        snapshot = repository.get_latest(actuator_id, station)
        return snapshot.model_dump(mode="json") if snapshot else {"status": "not_found"}

    return {"get_latest_measurements": get_latest_measurements}
