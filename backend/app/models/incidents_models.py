from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Incident(BaseModel):
    id: str                          # "INC-001"
    
    # Zone info
    zone_id: str                     # "Z3"
    zone_accident_frequency: float   # 0.0–1.0, how often this zone has incidents
    
    # Incident type + severity
    type: str                        # "road_accident" | "crowd_gathering" | "fallen_person" | "intrusion" | "fire" | "earthquake"
    severity: float                  # 1–10, you rate this per type (earthquake=9, fire=8, etc.)
    
    # Camera info
    camera_id: str                   # "CAM-06"
    camera_coverage: int             # how many people this camera covers (its zone population)
    people_in_frame: int             # actual count YOLO detected right now
    
    # Location
    lat: Optional[float] = None
    lng: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    def __init__(self, **data):
        super().__init__(**data)
        if self.lat is None and self.latitude is not None:
            self.lat = self.latitude
        if self.lng is None and self.longitude is not None:
            self.lng = self.longitude
            
    # Confidence + time
    detect_confidence: float         # 0.0–1.0, raw from YOLO
    timestamp: datetime
    
    # These get filled in by the backend, Person A doesn't send them
    decision_confidence: Optional[float] = None
    priority_score: Optional[float] = None
    status: str = "pending"
    assigned_drone: Optional[str] = None
    eta_seconds: Optional[float] = None