import math
from datetime import datetime

def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in meters between two lat/lng coordinates"""
    R = 6371000  # radius of Earth in meters
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

async def dedup_or_merge(db, incident):
    """
    Check if a similar incident exists within 200m and same type.
    If so, boosts its confidence using Multi-Cam bonus and returns its ID.
    
    Merge criteria:
    - Same incident type (e.g., both "road_accident")
    - Distance ≤ 200 meters
    - Time window ≤ 5 minutes (to avoid merging unrelated incidents)
    """
    from datetime import datetime, timedelta
    
    # Fetch recent incidents (including human-reviewed ones within time window)
    five_min_ago = datetime.utcnow() - timedelta(minutes=5)
    cursor = db.incidents.find({
        "status": {"$in": ["pending", "queued", "auto", "human"]},
        "timestamp": {"$gte": five_min_ago}  # Within last 5 minutes
    })
    recent_incidents = await cursor.to_list(length=200)
    
    for existing in recent_incidents:
        # Only merge incidents of same type
        if existing.get("type") != incident.type:
            continue
            
        dist = haversine(incident.lat, incident.lng, existing['lat'], existing['lng'])
        if dist <= 200:
            # Match found within 200 meters and same type! Merge them.
            # Boost decision confidence and flag with multi_cam_bonus for priority bumps
            new_conf = min(1.0, existing.get('decision_confidence', 0.5) * 1.25)
            new_priority = max(incident.priority_score, existing.get('priority_score', 0))
            await db.incidents.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "decision_confidence": new_conf, 
                    "multi_cam_bonus": 1.5,
                    "priority_score": new_priority,
                    "people_in_frame": max(incident.people_in_frame, existing.get('people_in_frame', 0))
                }}
            )
            return existing['id']
            
    return None