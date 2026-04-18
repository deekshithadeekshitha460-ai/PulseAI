from collections import defaultdict, deque
import time
import threading

SENSORS = ["temperature_C", "vibration_mm_s", "rpm", "current_A"]

# Keep last 15 readings per machine for drift detection
reading_history = defaultdict(lambda: deque(maxlen=15))

# Count consecutive anomalies per machine (for transient suppression)
consecutive_anomaly_count = defaultdict(int)

# Track recent alerts for cross-machine correlation
recent_alert_log = defaultdict(list)
log_lock = threading.Lock()

# An alert must persist for 3 consecutive readings before we fire it
CONSECUTIVE_THRESHOLD = 3


def compute_sigma(value, mean, std):
    """
    Sigma = how many standard deviations away from normal.
    0-1σ = totally normal
    1-2σ = slightly unusual
    2-3σ = anomalous
    3σ+  = very anomalous
    """
    return abs(value - mean) / std


def detect_drift(machine_id, sensor):
    """
    Drift = the sensor is slowly and consistently moving in one direction.
    Not a sudden spike, but a creeping change.
    Returns: (is_drifting, rate_per_reading, direction)
    """
    history = reading_history[machine_id]
    if len(history) < 6:
        return False, 0.0, ""

    values = [r.get(sensor, 0) for r in list(history)][-10:]
    diffs = [values[i+1] - values[i] for i in range(len(values)-1)]
    avg_change = sum(diffs) / len(diffs)

    # Use a more robust check: at least 80% same direction
    pos_diffs = [d for d in diffs if d > 0]
    neg_diffs = [d for d in diffs if d < 0]
    
    is_drifting = False
    direction = ""
    
    if len(pos_diffs) >= 7 and avg_change > 0.1:
        is_drifting = True
        direction = "rising"
    elif len(neg_diffs) >= 7 and avg_change < -0.1:
        is_drifting = True
        direction = "falling"

    if is_drifting:
        return True, round(avg_change, 3), direction

    return False, 0.0, ""


def estimate_time_to_failure(machine_id, sensor, current_value, baseline):
    """
    If a sensor is drifting upward, predict when it'll cross the danger threshold.
    Returns minutes until failure (or None if not drifting up).
    """
    is_drifting, rate, direction = detect_drift(machine_id, sensor)
    if not is_drifting or direction != "rising":
        return None

    # Danger threshold = mean + 4 standard deviations
    danger_threshold = baseline["mean"] + 4 * baseline["std"]
    gap = danger_threshold - current_value

    if gap <= 0:
        return 0  # already past threshold

    # rate is per reading, 1 reading = 1 second
    seconds_remaining = gap / abs(rate)
    minutes = round(seconds_remaining / 60, 1)
    return minutes


def detect_compound_failure(triggered_sensors, drifts):
    """
    Evaluates complex failure signatures (Fingerprints).
    A fingerprint matches if:
    1. At least one of its core sensors is triggered.
    2. All of its trend requirements (rising/falling/stable) are met.
    """
    # Fingerprint Registry (Integrated from MITRE-style design)
    FINGERPRINTS = [
        {
            "id": "PF-01",
            "name": "Lubrication Starvation (Bearing)",
            "patterns": {"vibration_mm_s": "rising", "current_A": "rising", "temperature_C": "stable"},
            "boost": 0.25
        },
        {
            "id": "PF-02",
            "name": "Heavy Stator/Motor Overload",
            "patterns": {"current_A": "rising", "temperature_C": "rising", "rpm": "falling"},
            "boost": 0.30
        },
        {
            "id": "PF-03",
            "name": "Dynamic Resonance Instability",
            "patterns": {"vibration_mm_s": "rising", "rpm": "stable"},
            "boost": 0.15
        },
        {
            "id": "PF-04",
            "name": "Cooling System Impairment",
            "patterns": {"temperature_C": "rising", "current_A": "stable"},
            "boost": 0.20
        }
    ]

    best_match = None
    max_confidence = 0

    # Get the state of every sensor: rising, falling, or stable
    # Default to 'stable' if no drift is explicitly detected
    sensor_trends = {s: "stable" for s in SENSORS}
    for d in drifts:
        sensor_trends[d["sensor"]] = d["direction"]

    triggered_names = {t["sensor"] for t in triggered_sensors}

    for fp in FINGERPRINTS:
        # 1. Check if at least one sensor in the pattern is actually anomalous (triggered)
        if not any(s in triggered_names for s in fp["patterns"].keys()):
            continue

        # 2. Check if all trends in the pattern match the current state
        match_count = 0
        total_criteria = len(fp["patterns"])
        
        for sensor, expected_trend in fp["patterns"].items():
            if sensor_trends.get(sensor) == expected_trend:
                match_count += 1
        
        # Calculate fingerprint confidence (0.0 to 1.0)
        confidence = match_count / total_criteria
        
        # We only consider it a 'match' if at least 2/3 of the pattern matches
        if confidence >= 0.66 and (not best_match or confidence > max_confidence):
            best_match = fp
            max_confidence = confidence

    if best_match:
        return {
            "id": best_match["id"],
            "name": best_match["name"],
            "boost": best_match["boost"],
            "match_confidence": round(max_confidence * 100, 1)
        }

    return None


def check_cross_machine_correlation(machine_id, sensor):
    """
    Identifies if a sensor anomaly is occurring synchronously 
    across multiple machines (Systemic Correlation).
    Returns: (list_of_correlated_machines, systemic_type)
    """
    SYSTEMIC_TYPES = {
        "temperature_C":  {"id": "S-01", "name": "Facility Cooling / Ambient Thermal Failure"},
        "current_A":      {"id": "S-02", "name": "Main Power Supply / Phase Fluctuation"},
        "vibration_mm_s": {"id": "S-03", "name": "Structural Resonance / Floor Vibration"},
        "rpm":            {"id": "S-04", "name": "Grid Frequency Instability"}
    }

    with log_lock:
        now = time.time()
        # Clean old entries (> 60s)
        for mid in list(recent_alert_log.keys()):
            recent_alert_log[mid] = [
                a for a in recent_alert_log[mid]
                if now - a["time"] < 60
            ]

        correlated = [
            mid for mid, alerts in recent_alert_log.items()
            if mid != machine_id and
            any(a["sensor"] == sensor for a in alerts)
        ]
        
        systemic_meta = SYSTEMIC_TYPES.get(sensor) if correlated else None
        return correlated, systemic_meta


def analyze(machine_id, reading, baselines):
    """
    Main analysis function. Call this every time a new reading arrives.
    Returns a dict with all findings.
    """
    # Add reading to history buffer
    reading_history[machine_id].append(reading)

    if machine_id not in baselines:
        return {"risk_score": 0, "triggered": [], "drift_flags": [],
                "compound": None, "confidence": 0,
                "correlated_machines": [], "severity": "LOW"}

    baseline = baselines[machine_id]
    triggered = []
    drift_flags = []
    max_sigma = 0

    for sensor in SENSORS:
        if sensor not in reading or sensor not in baseline:
            continue

        value = reading[sensor]
        mean  = baseline[sensor]["mean"]
        std   = baseline[sensor]["std"]
        sigma = compute_sigma(value, mean, std)

        # Flag as anomalous if more than 2 standard deviations from normal
        if sigma > 2.0:
            triggered.append({
                "sensor": sensor,
                "value":  round(value, 2),
                "mean":   round(mean, 2),
                "sigma":  round(sigma, 2)
            })
            max_sigma = max(max_sigma, sigma)

            # Log this for cross-machine correlation check
            with log_lock:
                recent_alert_log[machine_id].append({
                    "sensor": sensor,
                    "time":   time.time()
                })

        # Always check for drift, even if not yet anomalous
        is_drifting, rate, direction = detect_drift(machine_id, sensor)
        if is_drifting:
            ttf = estimate_time_to_failure(machine_id, sensor, value, baseline[sensor])
            drift_flags.append({
                "sensor":    sensor,
                "rate":      rate,
                "direction": direction,
                "ttf_min":   ttf
            })

    # ── TRANSIENT SUPPRESSION ──────────────────────────────────────────
    # Don't alert on a single spike. Must be anomalous 3 readings in a row.
    if triggered:
        consecutive_anomaly_count[machine_id] += 1
    else:
        consecutive_anomaly_count[machine_id] = 0

    suppressed = consecutive_anomaly_count[machine_id] < CONSECUTIVE_THRESHOLD
    if suppressed:
        triggered = []  # too early to fire — might be noise

    # ── COMPOUND DETECTION ────────────────────────────────────────────
    compound_result = detect_compound_failure(triggered, drift_flags)
    compound_name = compound_result["name"] if compound_result else None
    compound_boost = compound_result["boost"] if compound_result else 0.0

    # ── CROSS-MACHINE CORRELATION ─────────────────────────────────────
    correlated_machines = []
    systemic_issue = None
    if triggered:
        for t in triggered:
            correlated, systemic = check_cross_machine_correlation(machine_id, t["sensor"])
            if correlated:
                correlated_machines.extend(correlated)
                systemic_issue = systemic # pick the last one triggered (heuristic)
    
    correlated_machines = list(set(correlated_machines))

    # ── RISK SCORE 0–100 ──────────────────────────────────────────────
    base_score = min(95, int((max_sigma / 5.0) * 100))
    risk_score = min(100, int(base_score * (1 + compound_boost)))

    # ── CONFIDENCE % ──────────────────────────────────────────────────
    # Persistence = consecutive readings (1 per second)
    persistence_sec = consecutive_anomaly_count[machine_id]
    
    # Pattern weight (up to 20%)
    pattern_weight = (compound_result["match_confidence"] * 0.2) if compound_result else 0
    
    # Persistence weight (up to 30%, caps at 5 minutes / 300s)
    persistence_weight = min(30.0, (persistence_sec / 300.0) * 30.0)
    
    # Signal weight (up to 50%)
    signal_weight = min(50.0, (max_sigma / 5.0) * 50.0)
    
    confidence = int(min(99, signal_weight + pattern_weight + persistence_weight))

    # ── SEVERITY CLASSIFICATION ───────────────────────────────────────
    def classify(score):
        if score >= 80: return "CRITICAL"
        if score >= 60: return "HIGH"
        if score >= 40: return "MEDIUM"
        return "LOW"

    return {
        "risk_score":          risk_score,
        "triggered":           triggered,
        "drift_flags":         drift_flags,
        "compound":            compound_name,
        "compound_result":     compound_result,
        "systemic":            systemic_issue,
        "confidence":          confidence,
        "persistence_sec":     persistence_sec,
        "correlated_machines": correlated_machines,
        "severity":            classify(risk_score)
    }