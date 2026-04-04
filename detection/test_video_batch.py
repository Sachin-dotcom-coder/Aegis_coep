"""
Non-interactive test for accident detection on Accidents_car.mp4
Logs all scoring details to console for analysis
"""

import sys
import os
import cv2
import numpy as np

# Add parent directory to path to enable relative imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.detector import Detector

def test_on_video(video_path, frame_skip=5):
    """Process video and log all accident detection scores"""
    
    print(f"\n[START] Loading video: {video_path}", flush=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Could not open: {video_path}", flush=True)
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"[INFO] FPS: {fps}, Total frames: {total}", flush=True)
    print(f"[INFO] Processing every {frame_skip} frames only (for speed)", flush=True)
    print(f"[INFO] Creating detector with debug=True", flush=True)
    
    detector = Detector(acc_debug=True)  # Enable debug mode for accident detector
    frame_num = 0
    processed_frames = 0
    incidents_found = []
    
    print(f"\n[START] Processing {video_path}", flush=True)
    print(f"   FPS: {fps}, Total frames: {total}", flush=True)
    print("="*70 + "\n", flush=True)
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print(f"[END] Reached end of video at frame {frame_num}", flush=True)
                break
            
            frame_num += 1
            
            # Skip frames for speed
            if frame_num % frame_skip != 0:
                continue
            
            processed_frames += 1
            
            # Process frame (will print debug info to console)
            print(f"[FRAME {frame_num}] Processing...", flush=True)
            annotated, incidents = detector.process_frame(frame)
            
            # Log any detected incidents
            for inc in incidents:
                if inc["type"] == "road_accident":
                    incidents_found.append({
                        "frame": frame_num,
                        "severity": inc["severity"],
                        "confidence": inc["detect_confidence"]
                    })
                    print(f"\n🚨 INCIDENT DETECTED AT FRAME {frame_num}", flush=True)
                    print(f"   Severity: {inc['severity']}", flush=True)
                    print(f"   Confidence: {inc['detect_confidence']:.3f}", flush=True)
                    print(flush=True)
            
            # Show progress
            if processed_frames % 10 == 0:
                print(f"✓ Processed {processed_frames} sampled frames (at frame {frame_num}/{total})...", flush=True)
    except Exception as e:
        print(f"[ERROR] Exception during processing: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        cap.release()
    
    print("\n" + "="*70, flush=True)
    print(f"✅ PROCESSING COMPLETE", flush=True)
    print(f"   Total frames in video: {frame_num}", flush=True)
    print(f"   Frames processed: {processed_frames} (every {frame_skip})", flush=True)
    print(f"   Accidents detected: {len(incidents_found)}", flush=True)
    
    if incidents_found:
        print("\n   Detections:", flush=True)
        for inc in incidents_found:
            print(f"     Frame {inc['frame']}: Severity={inc['severity']}, Conf={inc['confidence']:.3f}", flush=True)
    else:
        print("   ⚠️  No accidents detected in video", flush=True)
    print("="*70 + "\n", flush=True)


if __name__ == "__main__":
    print("[MAIN] Starting test...", flush=True)
    video_path = "Accidents_car.mp4"
    test_on_video(video_path)
    print("[MAIN] Script completed", flush=True)
