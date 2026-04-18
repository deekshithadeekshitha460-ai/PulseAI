import time
import queue
import requests
import threading
from collections import defaultdict

from stream    import latest_readings, stream_status, start_all_streams
from baseline  import compute_baselines, adapt_baseline
from detector  import analyze
from explainer import explain

import logging
from flask import Flask, jsonify, request as flask_request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="dashboard")
CORS(app)  # Enable CORS for all routes

BASE_URL = "http://localhost:3000"

# ── Shared state ──────────────────────────────────────────────────────
alert_history    = []   # list of all alerts fired
scheduled_slots  = {}   # machine_id → scheduled slot string
acknowledged     = defaultdict(float)  # machine_id → timestamp of ack
state_lock       = threading.Lock()    # prevents race conditions
active_maintenance = set()               # machines currently being scheduled
nudge_count = 0                         # how many times we've refined baselines
nudge_lock = threading.Lock()
baselines_ref = [None]                  # global reference to baselines
maintenance_queue = queue.PriorityQueue()


def post_alert(machine_id, message, severity, confidence, reading):
    """
    Calls POST /alert on the hackathon server.
    This is how you tell the judges your agent detected something.

    Required fields per their README:
      machine_id, reason, reading (optional)
    """
    try:
        payload = {
            "machine_id": machine_id,
            "reason":     message,
            "reading":    reading
        }
        response = requests.post(
            f"{BASE_URL}/alert",
            json=payload,
            timeout=5
        )
        print(f"[ALERT SENT] {machine_id} -- {severity} "
              f"({confidence}%) -> HTTP {response.status_code}")
    except Exception as e:
        print(f"[ALERT ERROR] Failed to POST /alert: {e}")


def schedule_maintenance(machine_id):
    """
    Calls POST /schedule-maintenance — the bonus feature.
    The server auto-assigns the next available business morning slot.
    """
    try:
        payload = {"machine_id": machine_id}
        response = requests.post(
            f"{BASE_URL}/schedule-maintenance",
            json=payload,
            timeout=5
        )
        data = response.json()

        # Save the slot for the dashboard to display
        slot = data.get("slot") or data.get("scheduled_time") or "TBD"
        with state_lock:
            scheduled_slots[machine_id] = slot
        print(f"[MAINTENANCE SCHEDULED] {machine_id}: {slot}")

    except Exception as e:
        print(f"[SCHEDULE ERROR] Failed: {e}")
    finally:
        with state_lock:
            if machine_id in active_maintenance:
                active_maintenance.remove(machine_id)


def maintenance_worker():
    """
    Priority Queue Worker.
    Processes maintenance requests based on risk score (highest priority first).
    """
    while True:
        # Get next item from queue: (priority, machine_id)
        # We use -risk_score for priority because PriorityQueue is min-heap
        priority, machine_id = maintenance_queue.get()
        print(f"[QUEUE] Processing maintenance for {machine_id} (Priority: {-priority})")
        
        schedule_maintenance(machine_id)
        
        maintenance_queue.task_done()
        time.sleep(1) # Small delay between schedule calls to avoid API stress


def is_acknowledged(machine_id):
    """
    Returns True if this machine was acknowledged in the last 10 minutes.
    Acknowledged = operator said "I know, stop spamming me for 10 mins."
    """
    ack_time = acknowledged.get(machine_id, 0)
    return (time.time() - ack_time) < 600  # 600 seconds = 10 minutes


def on_reading(machine_id, reading, baselines_ref):
    """
    THIS IS THE HEART OF THE AGENT.
    Called every single second for every machine as readings arrive.
    Must complete in under 800ms.
    """
    # Skip if operator acknowledged this machine recently
    if is_acknowledged(machine_id):
        return

    baselines = baselines_ref[0]  # baselines_ref is a list wrapper for mutability

    # Analyze this reading
    result = analyze(machine_id, reading, baselines)

    # ── SELF-LEARNING (NUDGE) ──────────────────────────────────────────
    # If it's super healthy (risk < 20), nudge the baseline slightly
    if result["risk_score"] < 20:
        with nudge_lock:
            global nudge_count
            nudge_count += 1
            if nudge_count % 300 == 0:  # Log every 5 mins of healthy stream
                print(f"[SELF-LEARNING] PulseAI has refined {nudge_count} baselines based on recent healthy operations.")
        
        for sensor, val in reading.items():
            if sensor in SENSORS:
                baselines_ref[0] = adapt_baseline(baselines_ref[0], machine_id, sensor, val, type="nudge")

    # Only act on MEDIUM severity or above (score >= 40)
    if result["risk_score"] < 40:
        return

    message = explain(machine_id, result)

    # Store in alert history (for dashboard)
    alert_entry = {
        "machine_id":  machine_id,
        "severity":    result["severity"],
        "score":       result["risk_score"],
        "confidence":  result["confidence"],
        "compound":    result["compound"],
        "correlated":  result["correlated_machines"],
        "drift":       result["drift_flags"],
        "message":     message,
        "reading":     reading,
        "time":        time.strftime("%H:%M:%S"),
        "acknowledged": False
    }

    with state_lock:
        alert_history.append(alert_entry)
        # Keep only last 100 alerts in memory
        if len(alert_history) > 100:
            alert_history.pop(0)

    print(f"\n{'='*60}")
    print(message)
    print(f"{'='*60}\n")

    # POST /alert to hackathon server (in background thread so it
    # doesn't block the next reading)
    threading.Thread(
        target=post_alert,
        args=(machine_id, message, result["severity"],
              result["confidence"], reading),
        daemon=True
    ).start()

    
    # POST /schedule-maintenance for HIGH and CRITICAL (via Priority Queue)
    if result["severity"] in ("HIGH", "CRITICAL"):
        should_queue = False
        with state_lock:
            if machine_id not in active_maintenance and machine_id not in scheduled_slots:
                active_maintenance.add(machine_id)
                should_queue = True
        
        if should_queue:
            # Negate risk_score so highest score is served first (PriorityQueue is min-heap)
            maintenance_queue.put((-result["risk_score"], machine_id))
            print(f"[QUEUE ADDED] {machine_id} added to priority queue (Risk: {result['risk_score']})")


# ── Flask server for dashboard ────────────────────────────────────────
# (Moved imports and app init to top)

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/status")
def status():
    with state_lock:
        return jsonify({
            "readings":  dict(latest_readings),
            "alerts":    list(alert_history[-30:]),
            "scheduled": dict(scheduled_slots),
            "streams":   dict(stream_status)
        })

@app.route("/acknowledge", methods=["POST"])
def acknowledge():
    """Dashboard calls this when operator clicks 'Acknowledge'."""
    data = flask_request.json
    machine_id = data.get("machine_id")
    if machine_id:
        acknowledged[machine_id] = time.time()
        with state_lock:
            # 1. Mark as acknowledged on dash
            for a in alert_history:
                if a["machine_id"] == machine_id:
                    a["acknowledged"] = True
            
            # 2. PERFORM EXPLICIT REFINEMENT
            # Find the latest reading that was alerted on
            latest_alert = next((a for a in reversed(alert_history) if a["machine_id"] == machine_id), None)
            if latest_alert and "reading" in latest_alert:
                reading = latest_alert["reading"]
                for sensor, val in reading.items():
                    if sensor in SENSORS:
                        baselines_ref[0] = adapt_baseline(
                            baselines_ref[0], machine_id, sensor, val, type="refinement"
                        )
                print(f"[REFINEMENT] Operator acknowledged {machine_id}. PulseAI has refined the baseline thresholds.")

        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400

def start_flask():
    """Run Flask quietly in background."""
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000, debug=False)


# ── Main entry point ──────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  PulseAI — Predictive Maintenance Agent")
    print("  Team SAHASTRIX | Hack Malenadu 2026")
    print("=" * 60)
    print()

    # Step 1: Load 7-day history and compute baselines
    print("Step 1: Loading machine baselines from 7-day history...")
    baselines = compute_baselines()
    global baselines_ref
    baselines_ref[0] = baselines
    print("Baselines ready.\n")

    # Step 2: Start Flask dashboard server
    print("Step 2: Starting dashboard API on http://localhost:5000...")
    threading.Thread(target=start_flask, daemon=True).start()
    
    # Start Maintenance Queue Worker
    threading.Thread(target=maintenance_worker, daemon=True).start()
    print("Dashboard and Priority Queue worker running.\n")

    # Step 3: Start all 4 machine streams
    print("Step 3: Connecting to all 4 machine streams...")
    start_all_streams(on_reading, baselines_ref)
    print("All streams started. Agent is now running.\n")
    print("Open dashboard/index.html in your browser to see the live view.")
    print("Press Ctrl+C to stop.\n")

    # Step 4: Keep the main thread alive forever
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nAgent stopped.")

if __name__ == "__main__":
    main()