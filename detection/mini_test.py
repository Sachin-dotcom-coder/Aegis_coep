#!/usr/bin/env python3
"""
Minimal test - show what's happening frame by frame
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
from detection.incident_detectors import AccidentDetector

print("Starting test...")
cap = cv2.VideoCapture("Accidents_car.mp4")
detector = AccidentDetector(confirm_frames=1, debug=False)

frame_idx = 0
total_events = 0

while frame_idx < 100:
    ret, frame = cap.read()
    if not ret:
        print(f"Reached end of video at frame {frame_idx}")
        break
    
    frame_idx += 1
    
    # Run detector
    confirmed, events, vehicles = detector.detect(frame)
    
    # Every 10 frames, show totals
    if frame_idx % 10 == 0:
        print(f"Frame {frame_idx:3d}: {len(vehicles):2d} vehicles, events={len(events)}, confirmed={confirmed}")
    
    if events:
        print(f"\n✅ FRAME {frame_idx}: {len(events)} EVENT(S)!")
        for e in events:
            print(f"    Score={e['score']}, Vehicles={e['vehicles']}, Reason={e['reason'][:50]}")
        total_events += len(events)

print(f"\n{'='*100}")
print(f"Total frames analyzed: {frame_idx}")
print(f"Total events: {total_events}")

if total_events == 0:
    print(f"\n❌ NO EVENTS FOUND - Scoring must be broken or motion vectors are zero")
else:
    print(f"\n✅ Events detected - System working!")

cap.release()

