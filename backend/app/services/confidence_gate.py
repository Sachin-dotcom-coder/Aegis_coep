def gate(decision_confidence: float, incident_type: str = "unknown", detect_confidence: float = 0.0) -> str:
    # ── RULE 1: AUTO DISPATCH (Both >= 40%) ──────────────────────────────
    if detect_confidence >= 0.4 and decision_confidence >= 0.4:
        return "auto"
    
    # ── RULE 2: HUMAN CONFIRM -> AUTO-DEPLOY (One >= 40%) ────────────────
    elif detect_confidence >= 0.4 or decision_confidence >= 0.4:
        return "human"
    
    # ── RULE 3: HUMAN CONFIRM -> AUTO-ABORT (Both < 40%) ────────────────
    else:
        return "review"