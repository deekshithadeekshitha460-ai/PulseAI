import sys
import os
import time

# Add the current directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pulseai.detector import analyze
from pulseai.explainer import explain

def run_confidence_test():
    print("Testing Explainability Confidence Score...")

    baselines = {
        "CNC_01": {
            "temperature_C":  {"mean": 45.0, "std": 1.0},
            "vibration_mm_s": {"mean": 1.0, "std": 0.1}
        }
    }

    print("\n--- Simulating Consistent Multi-Sensor Anomaly (65 readings) ---")
    res = None
    for i in range(65):
        # Triggering both Temperature and Vibration
        res = analyze("CNC_01", {"temperature_C": 55.0, "vibration_mm_s": 2.5}, baselines)
    
    if res:
        print(f"Final Confidence: {res['confidence']}%")
        print(f"Persistence: {res['persistence_sec']}s")
        
        report = explain("CNC_01", res)
        print("\nGenerated Report Snippet:")
        print("-" * 60)
        print(report.split("\n")[0]) # Just the first line with the confidence reason
        print("-" * 60)
        
        first_line = report.split("\n")[0]
        if "confidence — based on" in first_line and "vibration + temperature" in first_line.lower() and "1 minutes" in first_line:
            print("\nVERIFIED: Descriptive confidence reasoning is accurate and detailed.")
        else:
            print("\nWARNING: Descriptive confidence reasoning might be missing or incorrect.")
    else:
        print("\nFAILURE: No analysis result generated.")

if __name__ == "__main__":
    run_confidence_test()
