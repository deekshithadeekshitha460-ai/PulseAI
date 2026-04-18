import queue
import time
import threading

def test_priority_logic():
    print("Testing Priority Queue logic for maintenance...")
    pq = queue.PriorityQueue()

    # Data: (negated_risk_score, machine_id)
    requests = [
        (-45, "MACHINE_LOW"),
        (-95, "MACHINE_CRITICAL"),
        (-60, "MACHINE_HIGH"),
        (-30, "MACHINE_MED")
    ]

    print("\nAdding requests to queue:")
    for priority, mid in requests:
        print(f"  - {mid} (Risk: {-priority})")
        pq.put((priority, mid))

    print("\nProcessing queue (orders should be sorted by risk):")
    processed = []
    while not pq.empty():
        p, mid = pq.get()
        print(f"  [WORKER] Scheduling {mid} (Priority: {-p})")
        processed.append(mid)
        pq.task_done()

    expected_order = ["MACHINE_CRITICAL", "MACHINE_HIGH", "MACHINE_LOW", "MACHINE_MED"]
    if processed == expected_order:
        print("\nSUCCESS: Priority Queue ordered machines correctly (Highest Risk first).")
    else:
        print(f"\nFAILURE: Incorrect order. Got {processed}, expected {expected_order}")

if __name__ == "__main__":
    test_priority_logic()
