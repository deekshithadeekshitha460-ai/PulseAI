import requests
import json
import threading
import time
import sseclient

BASE_URL    = "http://localhost:3000"
MACHINE_IDS = ["CNC_01", "CNC_02", "PUMP_03", "CONVEYOR_04"]

# Shared dict — all 4 threads write here, agent reads from here
latest_readings = {}
stream_status   = {m: "connecting" for m in MACHINE_IDS}


def connect_to_machine(machine_id, on_reading_callback, baselines_ref):
    """
    Connects to GET /stream/CNC_01 and calls on_reading_callback
    every time a new reading arrives (once per second).
    Auto-reconnects with exponential backoff if connection drops.
    """
    url     = f"{BASE_URL}/stream/{machine_id}"
    backoff = 2  # seconds to wait before retrying

    while True:
        try:
            stream_status[machine_id] = "connecting"
            print(f"[{machine_id}] Connecting to stream...")

            response = requests.get(url, stream=True, timeout=15)
            client   = sseclient.SSEClient(response)

            stream_status[machine_id] = "live"
            print(f"[{machine_id}] Stream connected.")
            backoff = 2  # reset backoff on successful connection

            for event in client.events():
                if not event.data:
                    continue
                
                try:
                    reading = json.loads(event.data)
                except json.JSONDecodeError:
                    print(f"[{machine_id}] Received malformed JSON: {event.data[:50]}")
                    continue

                latest_readings[machine_id] = reading

                # Process this reading immediately — time critical!
                start_ms = time.time() * 1000
                on_reading_callback(machine_id, reading, baselines_ref)
                elapsed_ms = time.time() * 1000 - start_ms

                # Warn if processing is getting slow
                if elapsed_ms > 800:
                    print(f"[WARNING] {machine_id} processing took "
                          f"{elapsed_ms:.0f}ms — must stay under 800ms!")

        except Exception as e:
            stream_status[machine_id] = "reconnecting"
            print(f"[{machine_id}] Stream lost: {e}. "
                  f"Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)  # max 30s between retries


def start_all_streams(on_reading_callback, baselines_ref):
    """
    Starts 4 threads, one per machine, all running simultaneously.
    Each thread calls connect_to_machine() independently.
    """
    for machine_id in MACHINE_IDS:
        t = threading.Thread(
            target=connect_to_machine,
            args=(machine_id, on_reading_callback, baselines_ref),
            daemon=True  # thread dies when main program exits
        )
        t.start()

    print("All 4 streams started in parallel.")