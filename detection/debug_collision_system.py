"""
Comprehensive debug tool for collision detection.
Shows real-time: vehicles, pairs, distances, scores, and detection logic.
"""

import cv2
import numpy as np
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ultralytics import YOLO
from collections import deque

video_path = Path(__file__).parent.parent / "Accidents_car.mp4"
if len(sys.argv) > 1:
    video_path = Path(sys.argv[1])

print(f"🎬 Video: {video_path}")
print(f"📊 Analyzing collision detection pipeline...")
print("=" * 100)

# Create detector
from detection.incident_detectors import AccidentDetector

detector = AccidentDetector(confirm_frames=1, debug=False)
cap = cv2.VideoCapture(str(video_path))

frame_count = 0
detections_found = []

while frame_count < 500:  # First 500 frames
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    
    # Run detector
    confirmed, events, vehicles = detector.detect(frame)
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Show frame summary
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if frame_count % 10 == 0:  # Every 10 frames
        print(f"\n[Frame {frame_count:4d}]")
        print(f"  Vehicles: {len(vehicles)}")
        
        # Calculate all pair distances
        if len(vehicles) >= 2:
            distances = []
            for i in range(len(vehicles)):
                for j in range(i + 1, len(vehicles)):
                    vi, vj = vehicles[i], vehicles[j]
                    dx = vi["cx"] - vj["cx"]
                    dy = vi["cy"] - vj["cy"]
                    dist = float(np.hypot(dx, dy))
                    distances.append(dist)
            
            if distances:
                min_d = min(distances)
                avg_d = np.mean(distances)
                print(f"  Pairs: {len(distances)} | Min dist: {min_d:.1f}px | Avg: {avg_d:.1f}px")
                
                # Show close pairs
                close_pairs = [(i, j, d) for k, (i, j, d) in enumerate(
                    [(i, j, float(np.hypot(vehicles[i]['cx']-vehicles[j]['cx'], 
                                           vehicles[i]['cy']-vehicles[j]['cy'])))
                     for i in range(len(vehicles))
                     for j in range(i+1, len(vehicles))]
                ) if d < 100]
                
                if close_pairs:
                    print(f"  🔴 Close pairs (<100px):")
                    for i, j, d in sorted(close_pairs, key=lambda x: x[2])[:3]:
                        vi, vj = vehicles[i], vehicles[j]
                        print(f"      [{i}] {vi['label']} ↔ [{j}] {vj['label']} = {d:.1f}px")
        
        if events:
            print(f"  ⚠️ EVENTS DETECTED: {len(events)}")
            for evt in events:
                print(f"      {evt['vehicles']} @ score={evt['score']}")
        
        if confirmed:
            print(f"  ✅ COLLISION CONFIRMED!")
            detections_found.append((frame_count, events))

cap.release()

print("\n" + "=" * 100)
print(f"📈 Summary (first 500 frames):")
print(f"  Total frames analyzed: {frame_count}")
print(f"  Total detections: {len(detections_found)}")

if detections_found:
    print(f"\n✅ Detections found at frames:")
    for frame_num, evts in detections_found:
        for evt in evts:
            print(f"    Frame {frame_num}: {evt['vehicles']} (score={evt['score']})")
else:
    print(f"\n❌ NO DETECTIONS FOUND")
    print(f"\n🔍 Debugging checklist:")
    print(f"  1. Are vehicles being detected? Check vehicle count above")
    print(f"  2. Are any pairs getting close (<100px)? Check distances above")
    print(f"  3. If YES to both but no events, scoring is broken")
    print(f"  4. If NO to 2, vehicles never get close enough")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DETAILED FRAME ANALYSIS (find the first collision frame)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n" + "=" * 100)
print("🔬 DETAILED ANALYSIS MODE: Finding first close pair...")
print("=" * 100)

cap = cv2.VideoCapture(str(video_path))
frame_count = 0
min_distance = float('inf')
closest_frame = None

while frame_count < 500:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    
    confirmed, events, vehicles = detector.detect(frame)
    
    # Find closest pair
    for i in range(len(vehicles)):
        for j in range(i + 1, len(vehicles)):
            vi, vj = vehicles[i], vehicles[j]
            dx = vi["cx"] - vj["cx"]
            dy = vi["cy"] - vj["cy"]
            dist = float(np.hypot(dx, dy))
            
            if dist < min_distance:
                min_distance = dist
                closest_frame = (frame_count, frame, vehicles, i, j, dist)

cap.release()

if closest_frame and closest_frame[5] < 100:
    frame_num, frame, vehicles, vi_idx, vj_idx, dist = closest_frame
    vi = vehicles[vi_idx]
    vj = vehicles[vj_idx]
    
    print(f"\n🎯 Closest pair found at Frame {frame_num}:")
    print(f"   Vehicle {vi_idx}: {vi['label']} @ ({vi['cx']:4d}, {vi['cy']:4d})")
    print(f"   Vehicle {vj_idx}: {vj['label']} @ ({vj['cx']:4d}, {vj['cy']:4d})")
    print(f"   Distance: {dist:.1f}px")
    
    # Calculate what scoring should be
    centre_dist = dist
    score = 0.0
    
    print(f"\n📊 Expected score calculation:")
    if centre_dist < 100:
        score += 0.4
        print(f"   ✓ centre_dist < 100: +0.4 → score = {score}")
    if centre_dist < 70:
        score += 0.3
        print(f"   ✓ centre_dist < 70: +0.3 → score = {score}")
    if centre_dist < 50:
        score += 0.3
        print(f"   ✓ centre_dist < 50: +0.3 → score = {score}")
    
    # Check approach (would need speed history)
    print(f"   ? Approach check: (not calculated in this view)")
    print(f"   Final score before approach: {score:.2f}")
    print(f"   Threshold: 0.7")
    print(f"   Result: {'✅ SHOULD DETECT' if score >= 0.7 else '❌ BELOW THRESHOLD'}")
else:
    print(f"\n❌ No close pairs found (all distances > 100px)")
    print(f"   Minimum distance across all frames: {min_distance:.1f}px")
