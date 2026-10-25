import unittest

from actuator_fault_agent.domain.models import MeasurementSnapshot, RiskLevel
from actuator_fault_agent.domain.rules import highest_risk, screen_measurements


class RulesTest(unittest.TestCase):
    def test_combined_mechanical_faults(self):
        snapshot = MeasurementSnapshot(
            actuator_id="A-1",
            station="EOL",
            values={
                "output_torque_nm": 90,
                "output_torque_min_nm": 100,
                "vibration_rms_mm_s": 5.0,
                "no_load_current_a": 3.3,
                "backlash_arcmin": 8.0,
                "backlash_max_arcmin": 6.0,
            },
        )
        findings = screen_measurements(snapshot)
        codes = {finding.code for finding in findings}
        self.assertEqual(
            codes,
            {"OUTPUT_TORQUE_LOW", "VIBRATION_HIGH", "NO_LOAD_CURRENT_HIGH", "BACKLASH_HIGH"},
        )
        self.assertEqual(highest_risk(findings), RiskLevel.MEDIUM)

    def test_safety_failure_is_critical(self):
        snapshot = MeasurementSnapshot(
            actuator_id="A-2",
            station="SAFETY",
            values={"insulation_test_pass": False, "hipot_test_pass": "NG"},
        )
        findings = screen_measurements(snapshot)
        self.assertEqual(findings[0].code, "ELECTRICAL_SAFETY_FAIL")
        self.assertEqual(highest_risk(findings), RiskLevel.CRITICAL)

    def test_bool_not_treated_as_number(self):
        snapshot = MeasurementSnapshot(
            actuator_id="A-3",
            station="EOL",
            values={"temperature_rise_c": True},
        )
        self.assertEqual(screen_measurements(snapshot), [])


if __name__ == "__main__":
    unittest.main()
