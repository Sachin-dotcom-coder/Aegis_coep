"""
Summary test for accident detection.
Shows only the final results without all the debug output.
"""

import sys
import os
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.detector import Detector

def test_on_video(video_path, frame_skip=5):
    """Process video and show only final summary"""
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Could not open: {video_path}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    detector = Detector(acc_debug=False)  # Disable debug mode for clean output
    frame_num = 0
    processed_frames = 0
    incidents_found = []
    
    print(f"\n📹 TESTING: {video_path}")
    print(f"   Total Frames: {total}")
    print(f"   FPS: {fps}")
    print(f"   Duration: {total/fps:.1f}s")
    print(f"   Processing every {frame_skip} frames...")
    print("=" * 70)
    
    while frame_num < total:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_num += 1
        
        if frame_num % frame_skip != 0:
            continue
        
        processed_frames += 1
        
        # Process frame silently
        import contextlib
        import io
        
        with contextlib.redirect_stdout(io.StringIO()):
            annotated, incidents = detector.process_frame(frame)
        
        # Collect incident data
        for inc in incidents:
            if inc["type"] == "road_accident":
                incidents_found.append({
                    "frame": frame_num,
                    "severity": inc["severity"],
                    "confidence": inc["detect_confidence"]
                })
        
        # Show progress
        if processed_frames % 20 == 0:
            print(f"  Progress: {processed_frames} sampled frames (~{frame_num}/{total})")
    
    cap.release()
    
    print("=" * 70)
    print(f"\n✅ RESULTS:\n")
    print(f"   Total frames processed: {processed_frames} (every {frame_skip} frames)")
    print(f"   Total video frames: {frame_num}")
    print(f"   Accidents detected: {len(incidents_found)}")
    
    if incidents_found:
        print(f"\n   Detections:")
        for inc in incidents_found:
            print(f"     • Frame {inc['frame']:4d}: Severity={inc['severity']:.1f}, Confidence={inc['confidence']:.3f}")
    else:
        print(f"\n   ⚠️  No accidents detected")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    test_on_video("Accidents_car.mp4", frame_skip=5)
