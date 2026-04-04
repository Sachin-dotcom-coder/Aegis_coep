"""
Quick diagnostic to identify the PRIMARY blockage in collision detection.

Run this first to narrow down where the problem is.

Usage:
    python -m detection.quick_diagnose test_video.mp4
"""

import sys
import cv2
import numpy as np
from collections import deque
from ultralytics import YOLO

def diagnose(source):
    """Quick check of the detection pipeline."""
    try:
        source = int(source)
    except (ValueError, TypeError):
        pass

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"❌ Could not open: {source}")
        return

    print(f"\n{'='*70}")
    print(f"COLLISION DETECTION DIAGNOSTIC")
    print(f"{'='*70}\n")

    # Load YOLO
    print("🔄 Loading YOLOv8m vehicle model...")
    try:
        model = YOLO("yolov8m.pt")
        print("✓ Model loaded\n")
    except Exception as e:
        print(f"❌ Failed to load model: {e}\n")
        return

    VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
    
    frame_num = 0
    vehicle_counts = []
    pair_counts = []
    distance_samples = []
    
    print("Scanning frames...")
    while frame_num < 500:  # Scan first 500 frames
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_num += 1
        
        if frame_num % 50 == 0:
            print(f"  • Frame {frame_num}...", end="\r")
        
        # Run detection
        results = model.track(frame, imgsz=416, persist=True, verbose=False)
        boxes = results[0].boxes
        
        if boxes is None:
            vehicle_counts.append(0)
            pair_counts.append(0)
            continue
        
        # Extract vehicles
        vehicles = []
        for box in boxes:
            cls_id = int(box.cls[0])
            if cls_id not in VEHICLE_CLASSES:
                continue
            
            track_id = int(box.id[0]) if box.id is not None else -1
            if track_id == -1:
                continue
            
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            
            vehicles.append({
                "track_id": track_id,
                "cx": cx,
                "cy": cy,
                "box": (x1, y1, x2, y2),
            })
        
        vehicle_counts.append(len(vehicles))
        
        # Calculate pair distances
        pair_count = 0
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                pair_count += 1
                vi, vj = vehicles[i], vehicles[j]
                dx = vi["cx"] - vj["cx"]
                dy = vi["cy"] - vj["cy"]
                centre_dist = float(np.hypot(dx, dy))
                distance_samples.append(centre_dist)
        
        pair_counts.append(pair_count)
    
    cap.release()
    
    print(f"\n{'='*70}")
    print(f"DIAGNOSTIC RESULTS ({frame_num} frames scanned)")
    print(f"{'='*70}\n")
    
    # 1. Vehicle detection
    avg_vehicles = np.mean(vehicle_counts) if vehicle_counts else 0
    max_vehicles = max(vehicle_counts) if vehicle_counts else 0
    frames_with_vehicles = sum(1 for c in vehicle_counts if c > 0)
    
    print(f"🚗 VEHICLE DETECTION:")
    print(f"   • Average vehicles per frame: {avg_vehicles:.1f}")
    print(f"   • Max vehicles in any frame: {max_vehicles}")
    print(f"   • Frames with vehicles: {frames_with_vehicles}/{frame_num} ({100*frames_with_vehicles/frame_num:.1f}%)")
    
    if frames_with_vehicles == 0:
        print(f"\n   ❌ BLOCKER #1: NO VEHICLES DETECTED")
        print(f"      → YOLO model may not be working or model path wrong")
        print(f"      → Check: 'yolov8m.pt' exists and weights loaded correctly")
        return
    elif avg_vehicles < 1:
        print(f"\n   ⚠️  WARNING: Vehicle detection very sparse")
    else:
        print(f"   ✓ Vehicles regularly detected\n")
    
    # 2. Pair formation
    avg_pairs = np.mean(pair_counts) if pair_counts else 0
    max_pairs = max(pair_counts) if pair_counts else 0
    
    print(f"👥 PAIR FORMATION:")
    print(f"   • Average pairs per frame: {avg_pairs:.1f}")
    print(f"   • Max pairs in any frame: {max_pairs}")
    
    if max_pairs == 0:
        print(f"\n   ❌ BLOCKER #2: NO PAIRS FORMED")
        print(f"      → Too few vehicles detected OR tracking not working")
        print(f"      → Check: ByteTrack IDs being assigned correctly")
        return
    elif avg_pairs < 0.5:
        print(f"\n   ⚠️  WARNING: Very few pairs forming")
    else:
        print(f"   ✓ Pairs forming regularly\n")
    
    # 3. Distance distribution
    if distance_samples:
        dist_close = sum(1 for d in distance_samples if d < 100)
        dist_medium = sum(1 for d in distance_samples if 100 <= d < 200)
        dist_far = sum(1 for d in distance_samples if d >= 200)
        
        print(f"📏 DISTANCE DISTRIBUTION:")
        print(f"   • Close (<100px):    {dist_close:5d} pairs ({100*dist_close/len(distance_samples):5.1f}%)")
        print(f"   • Medium (100-200px): {dist_medium:5d} pairs ({100*dist_medium/len(distance_samples):5.1f}%)")
        print(f"   • Far (>200px):      {dist_far:5d} pairs ({100*dist_far/len(distance_samples):5.1f}%)")
        print(f"   • Min distance: {min(distance_samples):.1f}px")
        print(f"   • Max distance: {max(distance_samples):.1f}px")
        print(f"   • Mean distance: {np.mean(distance_samples):.1f}px")
        print(f"   • Median distance: {np.median(distance_samples):.1f}px\n")
        
        if dist_close == 0:
            print(f"   ⚠️  WARNING: No vehicle pairs within 100px")
            print(f"      → Vehicles never get close in this video")
            print(f"      → Or timing/tracking is broken\n")
    
    print(f"{'='*70}")
    print(f"NEXT STEPS:")
    print(f"{'='*70}\n")
    print(f"IF vehicles detected + pairs form:")
    print(f"  1. Run full debug: python -m detection.debug_collisions {source}")
    print(f"  2. Check score thresholds and validator confirmation\n")
    print(f"IF no vehicles or no pairs:")
    print(f"  1. Verify 'yolov8m.pt' is in the project root")
    print(f"  2. Check if video has actual vehicles in it")
    print(f"  3. Try with a sample video where vehicles clearly collide\n")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    diagnose(source)
