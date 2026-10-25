from fastapi.testclient import TestClient

from actuator_fault_agent.api import app

client = TestClient(app)


def test_diagnosis_completes_for_medium_risk_case():
    response = client.post(
        "/v1/diagnoses",
        json={
            "question": "输出扭矩不足且空载电流升高，请给出排查顺序",
            "actuator_id": "RA-2407-018",
            "station": "EOL-02",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["trigger_source"] == "engineer"
    assert result["diagnosis"]["likely_causes"]
    assert "实时数据" in result["diagnostic_query"]


def test_critical_case_interrupts_and_resumes():
    response = client.post(
        "/v1/diagnoses",
        json={
            "question": "绝缘和耐压测试失败，如何处理",
            "actuator_id": "RA-2407-099",
            "station": "SAFETY-01",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "review_required"
    assert result["diagnosis"]["risk_level"] == "critical"

    resumed = client.post(
        f"/v1/diagnoses/{result['thread_id']}/resume",
        json={
            "approved": True,
            "reviewer": "quality-engineer",
            "note": "确认隔离并按安全流程检查",
        },
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"


def test_alarm_event_triggers_data_enriched_retrieval():
    response = client.post(
        "/v1/alarms/events",
        json={
            "event_id": "alarm-20261025-0001",
            "source_system": "eol-fault-detector",
            "actuator_id": "RA-2407-018",
            "station": "EOL-02",
            "product_model": "RA-60",
            "alarm_code": "EOL-TQ-LOW",
            "alarm_message": "输出扭矩低于下限并伴随异常振动",
            "severity": "medium",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["trigger_source"] == "alarm"
    assert result["event_id"] == "alarm-20261025-0001"
    assert result["measurements"]["source"] == "mock-eol"
    assert "EOL-TQ-LOW" in result["diagnostic_query"]
    assert "output_torque_nm=118.4" in result["diagnostic_query"]
    assert "输出扭矩不足" in result["diagnostic_query"]
    assert result["evidence"]
    assert result["diagnosis"]["likely_causes"]


def test_critical_alarm_requires_human_review_even_with_normal_measurements():
    response = client.post(
        "/v1/alarms/events",
        json={
            "event_id": "alarm-20261025-0002",
            "source_system": "safety-controller",
            "actuator_id": "RA-2407-021",
            "station": "EOL-02",
            "alarm_code": "SAFE-STOP",
            "alarm_message": "安全控制器触发紧急停止",
            "severity": "critical",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "review_required"
    assert result["diagnosis"]["risk_level"] == "critical"
    assert "critical" in result["review_payload"]["reason"]
