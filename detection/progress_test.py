#!/usr/bin/env python3
"""
Ultra-simple test - show progress step by step
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("1. Importing OpenCV...")
import cv2
print("[OK] OpenCV imported")

print("2. Opening video...")
cap = cv2.VideoCapture("Accidents_car.mp4")
if not cap.isOpened():
    print("[ERROR] Failed to open video")
    sys.exit(1)
print("[OK] Video opened")

print("3. Reading first frame...")
ret, frame = cap.read()
if not ret:
    print("[ERROR] Failed to read frame")
    sys.exit(1)
print(f"[OK] Frame read: {frame.shape}")

print("4. Creating detector (this loads YOLO model)...")
sys.stdout.flush()
from detection.incident_detectors import AccidentDetector
detector = AccidentDetector(confirm_frames=1, debug=False)
print("[OK] Detector created")

print("5. Running detection on first frame...")
sys.stdout.flush()
try:
    confirmed, events, vehicles = detector.detect(frame)
    print(f"[OK] Detection completed")
    print(f"   Vehicles: {len(vehicles)}")
    print(f"   Events: {len(events)}")
    print(f"   Confirmed: {confirmed}")
except Exception as e:
    print(f"[ERROR] Detection failed: {e}")
    import traceback
    traceback.print_exc()

print("6. Processing more frames...")
frame_count = 1
while frame_count < 30:
    ret, frame = cap.read()
    if not ret:
        break
    frame_count += 1
    confirmed, events, vehicles = detector.detect(frame)
    if frame_count % 5 == 0:
        print(f"   Frame {frame_count}: {len(vehicles)} vehicles, {len(events)} events")

print(f"\n[OK] Processed {frame_count} frames successfully")
cap.release()
