"""
Quick test: Process only first 300 frames to verify FIX 1 and FIX 2
"""

import sys
import os
import cv2
import io
import contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.detector import Detector

def quick_test(video_path, max_frames=300):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Could not open: {video_path}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    detector = Detector(acc_debug=False)
    frame_num = 0
    incidents_found = []
    
    print(f"\n🚀 QUICK TEST (first {max_frames} frames)")
    print("=" * 70)
    
    while frame_num < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_num += 1
        
        # Suppress output
        with contextlib.redirect_stdout(io.StringIO()):
            annotated, incidents = detector.process_frame(frame)
        
        for inc in incidents:
            if inc["type"] == "road_accident":
                incidents_found.append({
                    "frame": frame_num,
                    "severity": inc["severity"],
                    "confidence": inc["detect_confidence"]
                })
                print(f"  🚨 Frame {frame_num}: Accident detected (conf={inc['detect_confidence']:.3f})")
        
        if frame_num % 50 == 0:
            print(f"  ✓ Processed {frame_num} frames...")
    
    cap.release()
    
    print("=" * 70)
    print(f"\n📊 SUMMARY:")
    print(f"   Frames processed: {frame_num}")
    print(f"   Accidents found: {len(incidents_found)}")
    
    if incidents_found:
        print(f"\n   ✅ FIX 2 (COOLDOWN) IS {'WORKING' if len(incidents_found) <= 2 else 'NOT WORKING (too many detections)'}!")
        for inc in incidents_found:
            print(f"      • Frame {inc['frame']}: Conf={inc['confidence']:.3f}")
    else:
        print(f"   ⚠️  No accidents detected")
    print()

if __name__ == "__main__":
    quick_test("Accidents_car.mp4", max_frames=300)
