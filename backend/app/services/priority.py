import math
from datetime import datetime

def calculate_priority(incident) -> float:
    # Static fallback
    severity = getattr(incident, 'severity', 1.0)
    decision_confidence = getattr(incident, 'decision_confidence', 1.0)
    return round(severity * decision_confidence, 3)

def calculate_dynamic_priority(incident, distance_to_drone: float) -> float:
    """
    Full Priority Formula as per PRD:
    Score = (Severity × Zone Risk × Time Weight × Recency Boost × Multi-Cam Bonus) ÷ (1 + ETA Penalty)
    *Zone risk is baked into decision_confidence.
    """
    if isinstance(incident, dict):
        severity = float(incident.get('severity', 1.0))
        people = float(incident.get('people_in_frame', 0.0))
        decision_confidence = float(incident.get('decision_confidence', 1.0))
        multi_cam_bonus = float(incident.get('multi_cam_bonus', 1.0))
        timestamp_str = incident.get('timestamp', None)
    else:
        severity = float(getattr(incident, 'severity', 1.0))
        people = float(getattr(incident, 'people_in_frame', 0.0))
        decision_confidence = float(getattr(incident, 'decision_confidence', 1.0))
        multi_cam_bonus = float(getattr(incident, 'multi_cam_bonus', 1.0))
        timestamp_str = getattr(incident, 'timestamp', None)

    # Time weight (e.g. night vs day logic, placeholder implementation)
    time_weight = 1.0
    recency_boost = 1.0
    
    if timestamp_str:
        if isinstance(timestamp_str, str):
            try:
                # Strip out the Z timezone format to easily parse
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                # If night time (20:00 to 06:00), events like fire or intrusion weight heavier
                if dt.hour >= 20 or dt.hour <= 6:
                    time_weight = 1.3
                
                # Recency check (how old is the incident report compared to now)
                # Freshness factor out of 1.0
                age_minutes = (datetime.now(dt.tzinfo) - dt).total_seconds() / 60.0
                if age_minutes < 2.0:
                    recency_boost = 1.2
            except Exception:
                pass

    # Base priority (Severity × Zone Risk[baked in conf] × Time Weight × Recency Boost × Multi-Cam Bonus)
    # Plus crowd density mapping
    crowd_factor = (1.0 + people / 100.0)
    
    base_score = severity * crowd_factor * decision_confidence * time_weight * recency_boost * multi_cam_bonus
    
    # Distance penalty (ETA Penalty pseudo estimation)
    eta_penalty = distance_to_drone * 100.0 
    
    priority_score = base_score / (1.0 + eta_penalty)
    return round(priority_score, 3)