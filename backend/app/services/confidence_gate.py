def gate(decision_confidence: float) -> str:
    if decision_confidence >= 0.8:
        return "auto"
    elif decision_confidence >= 0.3:
        return "human"
    else:
        return "silent"