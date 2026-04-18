import sys
import os

# Add the current directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pulseai.baseline import adapt_baseline

def run_learning_test():
    print("Testing Self-Learning Baseline Adaptation...")

    # Start with a simple baseline
    baselines = {
        "MACHINE_01": {
            "temperature_C": {"mean": 100.0, "std": 10.0}
        }
    }

    initial_mean = baselines["MACHINE_01"]["temperature_C"]["mean"]
    print(f"Initial Mean: {initial_mean}")

    # 1. Test 'nudge' (continuous learning)
    # Simulate 10 readings at 110.0
    print("\n--- Simulating 10 'nudges' at 110.0 ---")
    for _ in range(10):
        baselines = adapt_baseline(baselines, "MACHINE_01", "temperature_C", 110.0, type="nudge")
    
    nudge_mean = baselines["MACHINE_01"]["temperature_C"]["mean"]
    print(f"Mean after nudges: {nudge_mean:.4f}")
    if nudge_mean > initial_mean:
        print("SUCCESS: Mean nudged upward.")
    else:
        print("FAILURE: Mean did not nudge.")

    # 2. Test 'refinement' (explicit acknowledgement)
    # Simulate one acknowledgment at 150.0
    print("\n--- Simulating 1 'refinement' at 150.0 ---")
    baselines = adapt_baseline(baselines, "MACHINE_01", "temperature_C", 150.0, type="refinement")
    
    refine_mean = baselines["MACHINE_01"]["temperature_C"]["mean"]
    print(f"Mean after refinement: {refine_mean:.4f}")
    
    # Calculate expected shift: alpha=0.05
    # new = (0.95 * nudge_mean) + (0.05 * 150)
    expected = (0.95 * nudge_mean) + (0.05 * 150)
    print(f"Expected Mean: {expected:.4f}")

    if abs(refine_mean - expected) < 0.0001:
        print("SUCCESS: Explicit refinement applied correctly.")
    else:
        print("FAILURE: Refinement shift incorrect.")

if __name__ == "__main__":
    run_learning_test()
