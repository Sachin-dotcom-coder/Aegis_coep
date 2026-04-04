"""
test_detection.py — Standalone visual test (no backend required)

Runs the full detection pipeline on a video file or webcam and shows
a live annotated window. Detected incidents are printed to the console.
Nothing is sent to any server.

Usage (run from the AegisAI/ root folder):
    python -m detection.test_detection                  # webcam
    python -m detection.test_detection test_video.mp4   # video file
    python -m detection.test_detection 0                # webcam (explicit)

Controls:
    Q          — quit
    SPACE      — pause / resume
    F          — toggle fire detection on/off
    A          — toggle accident detection on/off
    P          — toggle fall/pose detection on/off
    D          — toggle accident debug scores in terminal (shows per-pair scores)
    S          — save a screenshot to screenshots/

Usage with debug scores always on:
    python -m detection.test_detection test_video.mp4 --debug
"""

import sys
import os
import cv2
import datetime
from detection.detector import Detector

# ── ANSI colours for terminal output ─────────────────────────────────────────
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
RESET  = "\033[0m"

INCIDENT_COLOURS = {
    "fire":          RED,
    "road_accident": YELLOW,
    "fallen_person": CYAN,
}


def print_incident(inc: dict, frame_num: int):
    colour = INCIDENT_COLOURS.get(inc["type"], GREEN)
    print(
        f"\n{colour}{'─'*60}\n"
        f"  🚨 INCIDENT CONFIRMED  (frame {frame_num})\n"
        f"  Type       : {inc['type'].upper()}\n"
        f"  Zone       : {inc['zone_id']}  |  Severity : {inc['severity']}\n"
        f"  Confidence : {inc['detect_confidence']}\n"
        f"  Location   : lat={inc['lat']}, lng={inc['lng']}\n"
        f"  People     : {inc['people_in_frame']}\n"
        f"{'─'*60}{RESET}"
    )


def run(source, debug: bool = False):
    # Accept int (webcam) or string (file path / RTSP)
    try:
        source = int(source)
    except (ValueError, TypeError):
        pass

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"❌ Could not open: {source}")
        sys.exit(1)

    # Get video properties for the HUD
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    detector   = Detector(acc_debug=debug)
    frame_num  = 0
    paused     = False

    # Feature toggles
    enable_fire     = True
    enable_accident = True
    enable_pose     = True
    acc_debug       = debug   # live score printing for accidents

    os.makedirs("screenshots", exist_ok=True)

    print(f"\n{GREEN}✅ Detection started on: {source}{RESET}")
    print("   Q=quit  SPACE=pause  F=fire  A=accident  P=pose  D=debug-scores  S=screenshot\n")

    while True:
        # ── Keyboard ──────────────────────────────────────────────────────────
        key = cv2.waitKey(33) & 0xFF
        if key == ord("q"):
            break
        elif key == ord(" "):
            paused = not paused
            print("⏸  Paused" if paused else "▶  Resumed")
        elif key == ord("f"):
            enable_fire = not enable_fire
            print(f"🔥 Fire detection {'ON' if enable_fire else 'OFF'}")
        elif key == ord("a"):
            enable_accident = not enable_accident
            print(f"🚗 Accident detection {'ON' if enable_accident else 'OFF'}")
        elif key == ord("p"):
            enable_pose = not enable_pose
            print(f"🧍 Pose/fall detection {'ON' if enable_pose else 'OFF'}")
        elif key == ord("d"):
            acc_debug = not acc_debug
            detector.accident_detector._debug = acc_debug
            print(f"🔍 Accident debug scores {'ON' if acc_debug else 'OFF'}")
        elif key == ord("s"):
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"screenshots/frame_{frame_num}_{ts}.jpg"
            cv2.imwrite(path, annotated if frame_num > 0 else frame)
            print(f"📸 Screenshot saved: {path}")

        if paused:
            cv2.imshow("AegisAI — Detection Test (no backend)", annotated if frame_num > 0 else frame)
            continue

        # ── Read frame ────────────────────────────────────────────────────────
        ret, frame = cap.read()
        if not ret:
            print("\n📹 End of video.")
            break
        frame_num += 1

        # ── Temporarily disable detectors through the toggle flags ────────────
        # We swap references so the shared Detector class stays intact
        if not enable_fire:
            detector.fire_detector._validator._min = 9999   # effectively disable
        else:
            detector.fire_detector._validator._min = detector.fire_detector._validator.required_frames

        # Run detection (all three detectors inside)
        annotated, incidents = detector.process_frame(frame)

        # ── Manually suppress outputs for disabled detectors ──────────────────
        if not enable_fire:
            incidents = [i for i in incidents if i["type"] != "fire"]
        if not enable_accident:
            incidents = [i for i in incidents if i["type"] != "road_accident"]
        if not enable_pose:
            incidents = [i for i in incidents if i["type"] != "fallen_person"]

        # ── Print confirmed incidents ─────────────────────────────────────────
        for inc in incidents:
            print_incident(inc, frame_num)

        # ── HUD overlay ───────────────────────────────────────────────────────
        h, w = annotated.shape[:2]
        status_line = (
            f"Frame {frame_num}"
            + (f"/{total}" if total > 0 else "")
            + f"   Fire:{'ON' if enable_fire else 'OFF'}"
            + f"  Accident:{'ON' if enable_accident else 'OFF'}"
            + f"  Pose:{'ON' if enable_pose else 'OFF'}"
        )
        cv2.putText(annotated, status_line,
                    (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow("AegisAI — Detection Test (no backend)", annotated)

    cap.release()
    cv2.destroyAllWindows()
    print(f"\n{GREEN}✅ Done. {frame_num} frames processed.{RESET}")


if __name__ == "__main__":
    args   = [a for a in sys.argv[1:] if a != "--debug"]
    debug  = "--debug" in sys.argv
    source = args[0] if args else 0
    run(source, debug=debug)
