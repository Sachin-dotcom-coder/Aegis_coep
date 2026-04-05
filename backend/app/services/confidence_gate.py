def gate(decision_confidence: float, incident_type: str = "unknown", detect_confidence: float = 0.0) -> str:
    # Dedicated bypass for accident severity: If the raw YOLO model asserts >= 50%, force AUTO
    if detect_confidence >= 0.5:
        return "auto"
    elif decision_confidence >= 0.20:
        return "human"
    else:
        return "silent"