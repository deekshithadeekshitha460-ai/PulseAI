import sys
import os
import time

# Add the current directory to path so we can import pulseai modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pulseai.detector import analyze
from pulseai.explainer import explain

def run_test():
    print("Testing MITRE-style Incident Fingerprinting...")

    # Define some normal baselines
    baselines = {
        "MACHINE_01": {
            "temperature_C":  {"mean": 60.0, "std": 2.0},
            "vibration_mm_s": {"mean": 2.0, "std": 0.5},
            "rpm":            {"mean": 1500.0, "std": 10.0},
            "current_A":      {"mean": 10.0, "std": 1.0}
        }
    }

    # Simulate PF-01: Lubrication Starvation
    # Vib: rising, Curr: rising, Temp: stable
    print("\n--- Simulating PF-01: Lubrication Starvation ---")
    
    readings = []
    for i in range(10):
        readings.append({
            "temperature_C":  60.1,  # stable
            "vibration_mm_s": 2.1 + (i * 0.5), # rising quickly (total +4.5)
            "rpm":            1500,  # stable
            "current_A":      10.1 + (i * 0.4)  # rising quickly (total +3.6)
        })

    result = None
    for i, r in enumerate(readings):
        result = analyze("MACHINE_01", r, baselines)
        print(f"Reading {i+1}: Result: {result['compound'] or 'None'} (Risk: {result['risk_score']})")

    if result and result["compound_result"]:
        print(f"\nSUCCESS: Matched {result['compound_result']['id']} - {result['compound_result']['name']}")
        print(f"Match Confidence: {result['compound_result']['match_confidence']}%")
        
        report = explain("MACHINE_01", result)
        print("\nGenerated Report Snippet:")
        print("-" * 40)
        print(report)
        print("-" * 40)
    else:
        print("\nFAILURE: Did not match fingerprint PF-01")

if __name__ == "__main__":
    run_test()
