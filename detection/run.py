"""
 The entry point — the script you actually run from the terminal.

What it does:

Takes a video source as argument (file path, 0 for webcam, or RTSP URL)
Opens the video with OpenCV
Creates a Detector instance
Loops through every frame:
Calls detector.process_frame(frame)
If incidents come back → prints them + calls post_incident()
post_incident() adds a timestamp and POSTs the JSON to http://localhost:8000/incidents/
Shows the annotated video in a window (press Q to quit)
"""

import sys
import cv2
import requests
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

from detection.detector import Detector

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def post_incident(incident: dict):
    """POST one incident to the FastAPI backend."""
    incident["timestamp"] = datetime.datetime.utcnow().isoformat()
    try:
        resp = requests.post(f"{BACKEND_URL}/incidents/", json=incident, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        print(f"  📡 Backend response: {data}")
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Could not reach backend: {e}")


def run(source):
    """Main video loop."""
    # Accept int (webcam index) or string (file / RTSP URL)
    try:
        source = int(source)
    except (ValueError, TypeError):
        pass

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"❌ Could not open video source: {source}")
        sys.exit(1)

    detector = Detector()
    frame_num = 0

    print(f"✅ Starting detection on: {source}")
    print("   Press Q to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("📹 End of video / stream lost.")
            break

        frame_num += 1
        annotated, incidents = detector.process_frame(frame)

        for inc in incidents:
            print(f"\n🚨 INCIDENT CONFIRMED (frame {frame_num}): {inc['type']} in {inc['zone_id']}")
            print(f"   Confidence: {inc['detect_confidence']}  People: {inc['people_in_frame']}")
            post_incident(inc)

        cv2.imshow("AegisAI — Detection", annotated)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\n✅ Detection stopped.")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    run(source)
