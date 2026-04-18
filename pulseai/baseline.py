import requests
import pandas as pd
import numpy as np

BASE_URL = "http://localhost:3000"
MACHINE_IDS = ["CNC_01", "CNC_02", "PUMP_03", "CONVEYOR_04"]
SENSORS = ["temperature_C", "vibration_mm_s", "rpm", "current_A"]

def fetch_history(machine_id):
    """
    Calls GET /history/CNC_01 and returns a pandas DataFrame.
    A DataFrame is just a table — rows are readings, columns are sensors.
    """
    print(f"Fetching 7-day history for {machine_id}...")
    response = requests.get(f"{BASE_URL}/history/{machine_id}")
    data = response.json()   # converts JSON response to Python dict
    readings = data.get("readings", [])
    df = pd.DataFrame(readings)  # converts list to table
    print(f"  Got {len(df)} readings for {machine_id}")
    return df

def compute_baselines():
    """
    For each machine, for each sensor:
    - mean = average normal value
    - std  = how much it normally varies (standard deviation)
    Returns a nested dict: baselines["CNC_01"]["temperature_C"]["mean"]
    """
    baselines = {}
    for machine_id in MACHINE_IDS:
        df = fetch_history(machine_id)
        baselines[machine_id] = {}
        for sensor in SENSORS:
            if sensor not in df.columns:
                continue
            values = df[sensor].dropna()
            baselines[machine_id][sensor] = {
                "mean": float(values.mean()),
                "std":  float(max(values.std(), 0.01))  # never let std be 0
            }
            print(f"  {machine_id} {sensor}: "
                  f"mean={baselines[machine_id][sensor]['mean']:.2f}, "
                  f"std={baselines[machine_id][sensor]['std']:.2f}")
    return baselines

def adapt_baseline(baselines, machine_id, sensor, new_value):
    """
    Self-learning: slowly adjust baseline after each alert resolves.
    alpha=0.05 means we move 5% toward the new observation each time.
    """
    b = baselines[machine_id][sensor]
    alpha = 0.05
    b["mean"] = (1 - alpha) * b["mean"] + alpha * new_value
    return baselines

# Test: run this file directly to see baselines
if __name__ == "__main__":
    b = compute_baselines()
    print("\nBaselines computed successfully!")