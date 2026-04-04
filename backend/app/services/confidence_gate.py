def gate(decision_confidence: float) -> str:
    if decision_confidence >= 0.75:
        return "auto"
    elif decision_confidence >= 0.5:
        return "queued"
    else:
        return "human"