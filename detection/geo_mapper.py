"""
Converts pixel coordinates (where the person is in the frame) to real-world latitude/longitude and a named zone.

Why this matters: The backend schema requires lat, lng, zone_id, zone_accident_frequency, and camera_coverage. You can't POST an incident without them.

How it works:

Divides the camera frame into 4 zones (a 2×2 grid)
Each zone has a pixel bounding box + corresponding real-world lat/lng
When a person is detected at pixel (cx, cy), it finds which zone they're in
Returns the zone's lat/lng and metadata

IMPORTANT: lat/lng are based on CAMERA position, not pixel position.
All incidents from the same camera will have identical lat/lng (the camera's fixed location).
The zone changes based on pixel position, but coordinates don't.
"""

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Define your zones here.  Each zone covers a pixel region of the frame.
# Adjust these to match your actual camera layout / demo video.
# ---------------------------------------------------------------------------
@dataclass
class Zone:
    zone_id: str
    # Pixel bounding box within the frame (x1, y1, x2, y2)
    px_x1: int
    px_y1: int
    px_x2: int
    px_y2: int
    # Real-world centroid
    lat: float
    lng: float
    # How often this zone historically has incidents (0.0–1.0)
    accident_frequency: float
    # How many people this camera typically covers
    camera_coverage: int


# Demo zones — divide a 640×480 frame into a 2×2 grid
ZONES = [
    Zone("Z1", 0,   0,   320, 240, 18.38, 73.66, 0.3, 30),
    Zone("Z2", 320, 0,   640, 240, 18.38, 73.66, 0.5, 45),
    Zone("Z3", 0,   240, 320, 480, 18.38, 73.66, 0.7, 60),
    Zone("Z4", 320, 240, 640, 480, 18.38, 73.66, 0.4, 25),
]

DEFAULT_ZONE = Zone("Z1", 0, 0, 9999, 9999, 18.38, 73.66, 0.3, 30)

# ---------------------------------------------------------------------------
# Camera locations - Generate 25 cameras for hackathon simulation
# ---------------------------------------------------------------------------
CAMERA_LOCATIONS = {
    "CAM-01": (18.3800, 73.6600),
    "CAM-02": (18.6600, 74.0400),
    "CAM-03": (18.3800, 74.0400),
    "CAM-04": (18.6600, 73.6600),
    "CAM-05": (18.5200, 73.8500),
    "CAM-06": (18.4200, 73.7200),
    "CAM-07": (18.6000, 73.9800),
    "CAM-08": (18.4500, 73.8000),
    "CAM-09": (18.6300, 73.9200),
    "CAM-10": (18.4800, 73.7500),
    "CAM-11": (18.5800, 74.0200),
    "CAM-12": (18.4000, 73.9500),
    "CAM-13": (18.6500, 73.7000),
    "CAM-14": (18.5000, 74.0400),
    "CAM-15": (18.3800, 73.8800),
    "CAM-16": (18.6600, 73.8200),
    "CAM-17": (18.4400, 73.6800),
    "CAM-18": (18.6200, 74.0000),
    "CAM-19": (18.5500, 73.6600),
    "CAM-20": (18.4800, 74.0400),
    "CAM-21": (18.6400, 73.7800),
    "CAM-22": (18.4000, 74.0400),
    "CAM-23": (18.6600, 73.9500),
    "CAM-24": (18.3800, 74.0000),
    "CAM-25": (18.6600, 73.7300),
}


def get_zone(cx: float, cy: float) -> Zone:
    """Return the zone that contains pixel centre (cx, cy)."""
    for z in ZONES:
        if z.px_x1 <= cx < z.px_x2 and z.px_y1 <= cy < z.px_y2:
            return z
    return DEFAULT_ZONE


def pixel_to_latlon(cx: float, cy: float, camera_id: str = "CAM-01"):
    """
    Return (lat, lng, zone) for a given pixel centre.
    
    lat/lng are the CAMERA's fixed location (all incidents from this camera have same coords).
    zone is determined by pixel position within the frame.
    """
    zone = get_zone(cx, cy)
    
    # Get camera's fixed location
    if camera_id in CAMERA_LOCATIONS:
        lat, lng = CAMERA_LOCATIONS[camera_id]
    else:
        # Fallback to default zone centroid if camera not registered
        lat, lng = zone.lat, zone.lng
    
    return lat, lng, zone
