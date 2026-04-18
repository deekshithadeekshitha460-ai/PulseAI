SENSOR_META = {
    "temperature_C":  ("temperature",  "°C",   "thermal stress"),
    "vibration_mm_s": ("vibration",    "mm/s", "mechanical stress"),
    "rpm":            ("RPM",          "rpm",  "rotational deviation"),
    "current_A":      ("current draw", "A",    "motor load"),
}

FAILURE_MODES = [
    {
        "id": "PF-01",
        "name": "Lubrication Starvation (Bearing)",
        "patterns": {
            "vibration_mm_s": "rising",
            "current_A": "rising",
            "temperature_C": "stable"
        },
        "description": "High-frequency vibration and motor drag without thermal spikes. Classic signature of lubrication loss before friction heat builds up.",
        "action": "Immediate lubrication cycle. Inspect bearing housing for seal leaks."
    },
    {
        "id": "PF-02",
        "name": "Heavy Stator/Motor Overload",
        "patterns": {
            "current_A": "rising",
            "temperature_C": "rising",
            "rpm": "falling"
        },
        "description": "Simultaneous current and thermal rise with loss of rotational speed. Indicates the motor is physically bound or severely over-torqued.",
        "action": "Halt operation. Inspect drive-train for mechanical jams or electrical phase imbalance."
    },
    {
        "id": "PF-03",
        "name": "Dynamic Resonance Instability",
        "patterns": {
            "vibration_mm_s": "rising",
            "rpm": "stable"
        },
        "description": "Vibration intensity increases while RPM remains steady. Suggests operation at a natural frequency of the machine structure.",
        "action": "Adjust operating frequency (RPM) by ±5%. Verify torque on mounting bolts."
    },
    {
        "id": "PF-04",
        "name": "Cooling System Impairment",
        "patterns": {
            "temperature_C": "rising",
            "current_A": "stable"
        },
        "description": "Temperature rise detected while electrical load remains constant. Likely indicative of fan failure, coolant leak, or radiator clogging.",
        "action": "Check cooling fans and heat sinks. Clean airflow obstructions immediately."
    }
]

def get_root_cause(triggered_sensors, compound_result=None):
    """
    Correlates multiple sensor triggers to identify a likely failure mode.
    Prioritizes matched Compound Fingerprints.
    """
    if compound_result:
        for mode in FAILURE_MODES:
            if mode["id"] == compound_result["id"]:
                # Add the match confidence to the mode for display
                mode_copy = mode.copy()
                mode_copy["match_confidence"] = compound_result["match_confidence"]
                return mode_copy
    
    # Fallback to simple membership check (if detector didn't find a fingerprint)
    sensor_names = {t["sensor"] for t in triggered_sensors}
    for mode in FAILURE_MODES:
        if "sensors" in mode and mode["sensors"].issubset(sensor_names):
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
    hypothesis = get_root_cause(triggered, analysis.get("compound_result"))
    if hypothesis:
        lines.append(f"\n[DIAGNOSTIC HYPOTHESIS]")
        if "id" in hypothesis:
            lines.append(f"  {hypothesis['id']}: {hypothesis['name']}")
            if "match_confidence" in hypothesis:
                lines.append(f"  Confidence: {hypothesis['match_confidence']}%")
        else:
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

    # 3. PREDICTIVE TIMELINE
    # Find the most urgent drift (shortest TTF)
    urgent_drift = None
    if drift:
        valid_ttfs = [d for d in drift if d["ttf_min"] is not None]
        if valid_ttfs:
            urgent_drift = min(valid_ttfs, key=lambda x: x["ttf_min"])

    if urgent_drift:
        label, _, _ = SENSOR_META.get(urgent_drift["sensor"], (urgent_drift["sensor"], "", ""))
        mins = urgent_drift["ttf_min"]
        
        ttf_phrase = "in less than 1 minute" if mins == 0 else f"in approximately {mins} minutes"
        
        lines.append(f"\n[PREDICTIVE TIMELINE]")
        lines.append(f"  At current drift rate, {machine_id} will exceed safe {label} limits {ttf_phrase}.")

    # 4. SYSTEMIC CONTEXT
    if correlated:
        lines.append(f"\n[SYSTEMIC CONTEXT]")
        lines.append(f"  Identified correlated behavior on {', '.join(correlated)}. This may be a facility-wide power/cooling issue.")

    # 5. RECOMMENDED ACTION
    lines.append(f"\n[RECOMMENDED ACTION]")
    if hypothesis:
        lines.append(f"  {hypothesis['action']}")
    else:
        lines.append("  Visual inspection and routine maintenance check requested.")

    return "\n".join(lines)