SENSOR_META = {
    "temperature_C":  ("temperature",  "°C",   "thermal stress"),
    "vibration_mm_s": ("vibration",    "mm/s", "mechanical stress"),
    "rpm":            ("RPM",          "rpm",  "rotational deviation"),
    "current_A":      ("current draw", "A",    "motor load"),
}

FAILURE_MODES = [
    {
        "id": "bearing_wear",
        "name": "Advanced Bearing Degradation",
        "sensors": {"vibration_mm_s", "temperature_C"},
        "description": "Rising vibration paired with increased heat suggests a breakdown in bearing lubrication and friction-heavy metal contact.",
        "action": "Immediate lubrication check. Schedule bearing replacement within 48 hours."
    },
    {
        "id": "motor_overload",
        "name": "Motor Overload / Winding Heat",
        "sensors": {"current_A", "temperature_C"},
        "description": "Excessive current draw and thermal rise indicate the motor is working beyond its torque rating, likely due to a mechanical obstruction.",
        "action": "Reduce load immediately. Inspect the drive-train for physical jams or debris."
    },
    {
        "id": "mechanical_obstruction",
        "name": "Mechanical Transmission Drag",
        "sensors": {"current_A", "rpm"},
        "description": "Dropping RPM despite higher current suggests the motor is struggling to maintain speed against high resistance.",
        "action": "Inspect belts, gears, and pulley alignment for signs of slipping or binding."
    },
    {
        "id": "resonance",
        "name": "High-Frequency Resonance",
        "sensors": {"vibration_mm_s", "rpm"},
        "description": "Vibration spikes at specific RPM ranges suggest mechanical resonance or misalignment.",
        "action": "Perform dynamic balancing and check machine mounting bolts for loosening."
    }
]

def get_root_cause(triggered_sensors):
    """
    Correlates multiple sensor triggers to identify a likely failure mode.
    """
    sensor_names = {t["sensor"] for t in triggered_sensors}
    
    # Check for complex matches first
    for mode in FAILURE_MODES:
        if mode["sensors"].issubset(sensor_names):
            return mode
            
    # Default behavior: pick the most significant sensor's basic cause
    if triggered_sensors:
        top_sensor = max(triggered_sensors, key=lambda x: x["sigma"])
        return {
            "name": f"Isolated {top_sensor['sensor']} anomaly",
            "description": f"Significant deviation in {top_sensor['sensor']} without secondary sensor confirmation. Likely a transient spike or sensor calibration issue.",
            "action": "Monitor sensor trend. If deviation persists, perform manual calibration."
        }
    return None

def explain(machine_id, analysis):
    """
    Converts raw analysis numbers into a message a maintenance 
    engineer can actually understand and act on.
    """
    triggered  = analysis["triggered"]
    drift      = analysis["drift_flags"]
    compound   = analysis["compound"] # keeping for backward compatibility if needed
    confidence = analysis["confidence"]
    severity   = analysis["severity"]
    correlated = analysis["correlated_machines"]

    if not triggered and not drift:
        return f"{machine_id}: All readings within normal range."

    lines = [f"{machine_id} — {severity} alert ({confidence}% confidence)"]

    # 1. ROOT CAUSE REASONING
    hypothesis = get_root_cause(triggered)
    if hypothesis:
        lines.append(f"\n[DIAGNOSTIC HYPOTHESIS]")
        lines.append(f"  {hypothesis['name']}")
        lines.append(f"  {hypothesis['description']}")

    # 2. SENSOR EVIDENCE
    lines.append(f"\n[SENSOR EVIDENCE]")
    for t in triggered:
        label, unit, _ = SENSOR_META.get(t["sensor"], (t["sensor"], "", ""))
        lines.append(f"  • {label}: {t['value']}{unit} ({t['sigma']:.1f} sigma deviation)")

    for d in drift:
        label, unit, _ = SENSOR_META.get(d["sensor"], (d["sensor"], "", ""))
        ttf_str = ""
        if d["ttf_min"] is not None:
            ttf_str = " — Critical in < 1 min" if d["ttf_min"] == 0 else f" — projected failure in {d['ttf_min']}m"
        lines.append(f"  • {label} Trend: {d['direction']} at {abs(d['rate']):.2f}{unit}/s{ttf_str}")

    # 3. SYSTEMIC CONTEXT
    if correlated:
        lines.append(f"\n[SYSTEMIC CONTEXT]")
        lines.append(f"  Identified correlated behavior on {', '.join(correlated)}. This may be a facility-wide power/cooling issue.")

    # 4. RECOMMENDED ACTION
    lines.append(f"\n[RECOMMENDED ACTION]")
    if hypothesis:
        lines.append(f"  {hypothesis['action']}")
    else:
        lines.append("  Visual inspection and routine maintenance check requested.")

    return "\n".join(lines)