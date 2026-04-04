"""
Direct debug - patch AccidentDetector to log scoring details
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from ultralytics import YOLO
from detection.frame_validator import FrameValidator
from detection.incident_detectors import AccidentDetector, OpticalFlowAnalyzer

# Monkey-patch to add logging
original_pair_score = AccidentDetector._pair_score

def logged_pair_score(self, vi, vj, flow_mag, centre_dist, motion_i, motion_j):
    """Patched version with logging"""
    w_i = vi["box"][2] - vi["box"][0]
    h_i = vi["box"][3] - vi["box"][1]
    w_j = vj["box"][2] - vj["box"][0]
    h_j = vj["box"][3] - vj["box"][1]

    w_sum_half = (w_i + w_j) / 2.0
    h_sum_half = (h_i + h_j) / 2.0

    dx_abs   = abs(vi["cx"] - vj["cx"])
    dy_abs   = abs(vi["cy"] - vj["cy"])
    overlap_x = w_sum_half - dx_abs
    overlap_y = h_sum_half - dy_abs
    margin_x  = w_sum_half * 0.05
    margin_y  = h_sum_half * 0.05

    if overlap_x > -margin_x and overlap_y > -margin_y:
        pct_x  = min(1.0, max(0.0, overlap_x / w_sum_half)) if w_sum_half > 0 else 0
        pct_y  = min(1.0, max(0.0, overlap_y / h_sum_half)) if h_sum_half > 0 else 0
        bbox_s = (pct_x + pct_y) / 2.0
        if bbox_s == 0:
            bbox_s = 0.15
    else:
        bbox_s = 0.0

    avg_size  = (((vi["box"][2] - vi["box"][0])**2 + (vi["box"][3] - vi["box"][1])**2)**0.5 +
                 ((vj["box"][2] - vj["box"][0])**2 + (vj["box"][3] - vj["box"][1])**2)**0.5) / 2.0
    safe_dist = float(np.clip(avg_size * 1.5, 50, 200))
    dist_s    = float(np.clip(1.0 - centre_dist / safe_dist, 0.0, 1.0))

    if centre_dist < 150:
        dist_s = min(dist_s * 1.5, 1.0)

    # ===== NEW LOGIC (PURE PROXIMITY + APPROACH) =====
    score = 0.0
    
    # Strong proximity bonuses (CCTV fast collisions)
    if centre_dist < 100:
        score += 0.4
    if centre_dist < 70:
        score += 0.3
    if centre_dist < 50:
        score += 0.3
    
    # Are vehicles moving towards each other?
    dir_ij = np.array([vj["cx"] - vi["cx"], vj["cy"] - vi["cy"]], dtype=float)
    norm = np.linalg.norm(dir_ij)
    
    approach_bonus = 0.0
    if norm > 0:
        dir_unit = dir_ij / norm
        approach_i = float(np.dot(motion_i, dir_unit))
        approach_j = float(np.dot(motion_j, -dir_unit))
        
        if approach_i > 0 or approach_j > 0:
            approach_bonus = 0.3
            score += 0.3
    
    # Final threshold
    if score < 0.7:
        score = 0.0

    breakdown = {
        "bbox":  round(bbox_s,  3),
        "dist":  round(dist_s,  3),
        "accel": 0.0,
        "chaos": 0.0,
    }

    return score, breakdown

# Patch it
AccidentDetector._pair_score = logged_pair_score

# Now run detection
video_path = Path("Accidents_car.mp4")
print(f"🎬 Testing with: {video_path}")
print("=" * 100)

cap = cv2.VideoCapture(str(video_path))
detector = AccidentDetector(confirm_frames=1, debug=False)

frame_count = 0
event_count = 0
detection_frames = []

while frame_count < 200:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    
    confirmed, events, vehicles = detector.detect(frame)
    
    if events or confirmed:
        print(f"\n✅ Frame {frame_count}: {len(events)} events, confirmed={confirmed}")
        for evt in events:
            print(f"   {evt['vehicles']} @ score={evt['score']}")
            detection_frames.append((frame_count, evt))
            event_count += 1
    
    # Show every 20 frames
    if frame_count % 20 == 0:
        closest_dist = float('inf')
        for i in range(len(vehicles)):
            for j in range(i+1, len(vehicles)):
                vi, vj = vehicles[i], vehicles[j]
                dx = vi["cx"] - vj["cx"]
                dy = vi["cy"] - vj["cy"]
                d = float(np.hypot(dx, dy))
                closest_dist = min(closest_dist, d)
        
        print(f"[Frame {frame_count:3d}] Vehicles={len(vehicles):2d}, Closest pair={closest_dist:6.1f}px")

cap.release()

print("\n" + "=" * 100)
print(f"SUMMARY: {event_count} events detected in {frame_count} frames")
if detection_frames:
    print(f"✅ Events at frames: {[f[0] for f in detection_frames]}")
else:
    print(f"❌ NO EVENTS - SCORING OR THRESHOLD IS BROKEN")
    print(f"\n💡 Next step: Enable debug=True in AccidentDetector to see frame-by-frame scores")
