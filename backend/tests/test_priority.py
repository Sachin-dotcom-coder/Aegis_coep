import pytest
from app.services.priority import calculate_dynamic_priority
from datetime import datetime, timezone

def test_priority_no_timestamp():
    incident = {"severity": 1.0, "people_in_frame": 0, "decision_confidence": 0.9}
    # distance = 0 => 1/(1+0) = 1
    score = calculate_dynamic_priority(incident, 0.0)
    # expected = 1.0 * (1.0 + 0) * 0.9 * 1.0 (time) * 1.0 (recency) = 0.9
    assert score == 0.9

def test_priority_distance_penalty():
    incident = {"severity": 1.0, "people_in_frame": 0, "decision_confidence": 0.9}
    # distance = 0.1 => 1/(1 + 0.1*100) = 1/11
    score = calculate_dynamic_priority(incident, 0.1)
    # expected = 0.9 / 11 = 0.0818... -> 0.082 or similar
    assert score < 0.1

def test_priority_recency_boost():
    # Fresh incident: Midday to avoid time_weight
    now_dt = datetime.now(timezone.utc)
    # Force midday
    midday_dt = now_dt.replace(hour=12, minute=0, second=0)
    now_utc = midday_dt.isoformat().replace("+00:00", "Z")
    
    incident = {
        "severity": 1.0, 
        "people_in_frame": 0, 
        "decision_confidence": 1.0,
        "timestamp": now_utc
    }
    # Temporarily mock datetime.now in calculate_dynamic_priority is hard.
    # We can just use the current time if it's day, OR just fix the comparison.
    # Actually, calculate_dynamic_priority uses datetime.now() to check age.
    # If I use a past time, recency_boost should be 1.0.
    # If I use current time (now_utc), it should be 1.2.
    
    # Let's just use the current time for real and see.
    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    incident = {
        "severity": 1.0, 
        "people_in_frame": 0, 
        "decision_confidence": 1.0,
        "timestamp": now_utc
    }
    score_fresh = calculate_dynamic_priority(incident, 0.0)
    
    # Old incident: Midday to avoid time_weight
    incident_old = {
        "severity": 1.0, 
        "people_in_frame": 0, 
        "decision_confidence": 1.0,
        "timestamp": "2020-01-01T12:00:00Z" # Midday
    }
    score_old = calculate_dynamic_priority(incident_old, 0.0)
    
    # Compare WITHOUT time_weight affecting just one of them.
    # If it is currently night, fresh will have score 1.2 (recency) * 1.3 (time) = 1.56
    # If it is day, fresh will have 1.2.
    # Old one will always have 1.0 (no recency, no night-weight at 12:00).
    assert score_fresh > score_old

def test_priority_crowd_density():
    incident_low = {"severity": 1.0, "people_in_frame": 0, "decision_confidence": 1.0}
    incident_high = {"severity": 1.0, "people_in_frame": 50, "decision_confidence": 1.0}
    
    score_low = calculate_dynamic_priority(incident_low, 0.0)
    score_high = calculate_dynamic_priority(incident_high, 0.0)
    
    assert score_high == 1.5 # (1.0 + 50/100) * 1.0
    assert score_low == 1.0
