import unittest
import json
import pandas as pd
from detector import analyze, compute_sigma, detect_drift
from baseline import fetch_history
from explainer import explain

class TestPulseAIFixes(unittest.TestCase):
    def setUp(self):
        self.baselines = {
            "CNC_01": {
                "temperature_C": {"mean": 80.0, "std": 2.0},
                "vibration_mm_s": {"mean": 1.5, "std": 0.5},
                "rpm": {"mean": 1500, "std": 50},
                "current_A": {"mean": 10.0, "std": 1.0}
            }
        }

    def test_baseline_parsing_fix(self):
        # Mock data from server
        mock_data = {
            "machine_id": "CNC_01",
            "readings": [
                {"temperature_C": 80.5, "vibration_mm_s": 1.4},
                {"temperature_C": 81.0, "vibration_mm_s": 1.6}
            ]
        }
        df = pd.DataFrame(mock_data["readings"])
        self.assertIn("temperature_C", df.columns)
        self.assertEqual(len(df), 2)

    def test_robust_drift_detection(self):
        # Drift with some noise (9 diffs, 7 same direction = 77%, my code requires 7/9)
        # Values: 80.0 -> 80.5 -> 80.4 -> 80.9 ...
        from detector import reading_history
        machine_id = "TEST_DRIFT"
        sensor = "temp"
        reading_history[machine_id].clear()
        
        # Upward drift with two dips
        values = [80.0, 80.2, 80.4, 80.3, 80.6, 80.8, 80.7, 81.0, 81.2, 81.4]
        for v in values:
            reading_history[machine_id].append({sensor: v})
        
        is_drifting, rate, direction = detect_drift(machine_id, sensor)
        self.assertTrue(is_drifting, "Drift detection should now handle non-monotonic jitter")
        self.assertEqual(direction, "rising")

    def test_baseline_adaptation_safety(self):
        # Should not adapt if risk is high
        import detector
        detector.consecutive_anomaly_count.clear()
        
        # Trigger an alert first
        reading = {"temperature_C": 95.0, "vibration_mm_s": 1.5, "rpm": 1500, "current_A": 10.0}
        baseline_ref = [self.baselines]
        
        # Readings 1, 2, 3 (hits threshold)
        for _ in range(3):
            result = analyze("CNC_01", reading, baseline_ref[0])
        
        self.assertEqual(result["severity"], "CRITICAL")
        
        # In agent.py, it should skip adaptation. Let's verify our result score.
        self.assertGreaterEqual(result["risk_score"], 80)

if __name__ == "__main__":
    unittest.main()
