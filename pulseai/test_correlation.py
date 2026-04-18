import sys
import os
import time

# Add the current directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pulseai.detector import analyze
from pulseai.explainer import explain

def run_correlation_test():
    print("Testing Systemic Anomaly Correlation...")

    baselines = {
        "CNC_01": {"temperature_C": {"mean": 50.0, "std": 1.0}},
        "CNC_02": {"temperature_C": {"mean": 50.0, "std": 1.0}}
    }

    # 1. Trigger CNC_01 anomaly
    print("\n--- Triggering Temperature Spike on CNC_01 ---")
    res1 = None
    for _ in range(5): # enough for consecutive suppression
        res1 = analyze("CNC_01", {"temperature_C": 65.0}, baselines)
    
    print(f"CNC_01 Alert Fire: {res1['severity']} (Risk={res1['risk_score']})")

    # 2. Trigger CNC_02 anomaly (1 second later)
    print("\n--- Triggering Temperature Spike on CNC_02 ---")
    res2 = None
    for _ in range(5):
        res2 = analyze("CNC_02", {"temperature_C": 65.0}, baselines)

    print(f"CNC_02 Alert Fire: {res2['severity']} (Risk={res2['risk_score']})")
    
    if res2.get("systemic"):
        print(f"\nSUCCESS: Systemic Correlation Detected!")
        print(f"Issue: {res2['systemic']['id']} - {res2['systemic']['name']}")
        print(f"Correlated Victims: {res2['correlated_machines']}")
        
        report = explain("CNC_02", res2)
        print("\nGenerated Report Snippet:")
        print("-" * 60)
        print(report)
        print("-" * 60)
        
        if "[SYSTEMIC CONTEXT — INFRASTRUCTURE ALERT]" in report:
            print("\nVERIFIED: Systemic context integrated into engineers report.")
        else:
            print("\nWARNING: Systemic context section missing from report.")
    else:
        print("\nFAILURE: Systemic correlation not detected.")

if __name__ == "__main__":
    run_correlation_test()
