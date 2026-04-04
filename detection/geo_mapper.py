"""
Converts pixel coordinates (where the person is in the frame) to real-world latitude/longitude and a named zone.

Why this matters: The backend schema requires lat, lng, zone_id, zone_accident_frequency, and camera_coverage. You can't POST an incident without them.

How it works:

Divides the camera frame into 4 zones (a 2×2 grid)
Each zone has a pixel bounding box + corresponding real-world lat/lng
When a person is detected at pixel (cx, cy), it finds which zone they're in
Returns the zone's lat/lng and metadata
You should customise the zone
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
    Zone("Z1", 0,   0,   320, 240, 12.9716, 77.5946, 0.3, 30),
    Zone("Z2", 320, 0,   640, 240, 12.9720, 77.5950, 0.5, 45),
    Zone("Z3", 0,   240, 320, 480, 12.9710, 77.5940, 0.7, 60),
    Zone("Z4", 320, 240, 640, 480, 12.9725, 77.5955, 0.4, 25),
]

DEFAULT_ZONE = Zone("Z1", 0, 0, 9999, 9999, 12.9716, 77.5946, 0.3, 30)


def get_zone(cx: float, cy: float) -> Zone:
    """Return the zone that contains pixel centre (cx, cy)."""
    for z in ZONES:
        if z.px_x1 <= cx < z.px_x2 and z.px_y1 <= cy < z.px_y2:
            return z
    return DEFAULT_ZONE


def pixel_to_latlon(cx: float, cy: float):
    """
    Return (lat, lng, zone) for a given pixel centre.
    
    NEW: Interpolates lat/lng based on pixel position within the zone,
    instead of just returning zone centroid. This gives precise location data.
    """
    zone = get_zone(cx, cy)
    
    # Calculate position ratio within the zone (0.0 = left/top, 1.0 = right/bottom)
    zone_width = zone.px_x2 - zone.px_x1
    zone_height = zone.px_y2 - zone.px_y1
    
    # Prevent division by zero
    if zone_width == 0 or zone_height == 0:
        return zone.lat, zone.lng, zone
    
    # Ratio of pixel position within zone
    x_ratio = (cx - zone.px_x1) / zone_width  # 0.0-1.0
    y_ratio = (cy - zone.px_y1) / zone_height  # 0.0-1.0
    
    # Define corner coordinates for this zone
    # Top-left, top-right, bottom-left, bottom-right
    # These are estimated based on typical camera layout
    # You may need to adjust these based on your actual camera calibration
    
    # For demo: assume zones form a rectangle
    # Each zone gets interpolated based on its position
    lat_variance = 0.001  # ~111 meters per 0.001 degree
    lng_variance = 0.001
    
    # Calculate interpolated lat/lng
    interpolated_lat = zone.lat - (y_ratio - 0.5) * lat_variance
    interpolated_lng = zone.lng + (x_ratio - 0.5) * lng_variance
    
    return interpolated_lat, interpolated_lng, zone
