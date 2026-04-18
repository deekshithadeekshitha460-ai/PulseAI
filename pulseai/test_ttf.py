import sys
import os

# Add the current directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pulseai.detector import analyze
from pulseai.explainer import explain

def run_ttf_test():
    print("Testing Predictive Time-to-Failure (TTF) Estimation...")

    baselines = {
        "CNC_02": {
            "temperature_C":  {"mean": 45.0, "std": 1.0},
            "vibration_mm_s": {"mean": 1.0, "std": 0.1},
            "rpm":            {"mean": 720.0, "std": 5.0},
            "current_A":      {"mean": 8.0, "std": 0.5}
        }
    }

    # Simulate a slow drift in temperature
    # Danger threshold = 45 + 4*1 = 49
    # Start at 46, drift at 0.1 per reading
    # Gap = 49 - 46 = 3. 
    # TTF = 3 / 0.1 = 30 seconds = 0.5 minutes
    
    print("\n--- Simulating Temperature Drift on CNC_02 ---")
    readings = []
    for i in range(15):
        readings.append({
            "temperature_C":  46.0 + (i * 0.1),
            "vibration_mm_s": 1.0,
            "rpm":            720,
            "current_A":      8.0
        })

    result = None
    for i, r in enumerate(readings):
        result = analyze("CNC_02", r, baselines)
        # Note: TTF only starts showing up once we have 6 readings for drift detection
        ttf = None
        if result["drift_flags"]:
            ttf = result["drift_flags"][0]["ttf_min"]
        print(f"Reading {i+1}: Temp={r['temperature_C']:.1f}, TTF={ttf} min")

    if result and any(d["ttf_min"] is not None for d in result["drift_flags"]):
        print("\nSUCCESS: TTF estimation active.")
        report = explain("CNC_02", result)
        print("\nGenerated Report Snippet:")
        print("-" * 60)
        print(report)
        print("-" * 60)
        
        if "[PREDICTIVE TIMELINE]" in report and "exceed safe temperature limits" in report:
            print("\nVERIFIED: Predictive Timeline wording matches user request.")
        else:
            print("\nWARNING: Predictive Timeline wording or section missing.")
    else:
        print("\nFAILURE: TTF estimation did not trigger.")

if __name__ == "__main__":
    run_ttf_test()
