"""
Comprehensive collision detection debugging script.
Instruments the entire pipeline to show where detection fails.

Usage:
    python -m detection.debug_collisions test_video.mp4

This will show:
    - Vehicle detection counts per frame
    - Tracked vehicle IDs
    - All pair scores (even low ones)
    - Why pairs are filtered/skipped
    - Threshold passes/fails
    - Validator state
"""

import sys
import os
import cv2
import numpy as np
from collections import defaultdict, deque
from detection.detector import Detector
from detection.incident_detectors import AccidentDetector
from ultralytics import YOLO

# ANSI colors
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

class DebugAccidentDetector(AccidentDetector):
    """Instrumented accident detector that logs all decisions."""
    
    def detect(self, frame: np.ndarray) -> tuple[bool, list[dict], list[dict]]:
        """Verbose version of detect() with detailed logging."""
        results  = self._model.track(
            frame, imgsz=416, persist=True, verbose=False
        )
        vehicles = self._extract_vehicles(results[0].boxes)
        vehicles = self._dedup_vehicles(vehicles)

        flow_mag = self._flow_analyzer.update(frame)
        events: list[dict] = []

        print(f"\n{'='*80}")
        print(f"FRAME ANALYSIS")
        print(f"{'='*80}")
        print(f"🚗 Vehicles detected: {len(vehicles)}")
        
        if len(vehicles) == 0:
            print(f"{RED}❌ NO VEHICLES DETECTED - CAN'T SCORE PAIRS{RESET}")
            return False, [], vehicles

        # List all vehicles
        for v in vehicles:
            print(f"  • #{v['track_id']}: {v['label']:8s} @ ({v['cx']:4.0f}, {v['cy']:4.0f}) "
                  f"conf={v['conf']:.2f} speed={v['speed']:.4f}")

        # ── Traffic-light guard ────────────────────────────────────────────────
        if len(vehicles) >= 3:
            n_stopped = sum(
                1 for v in vehicles
                if self._rmean_helper(
                    self._speed_histories.get(v["track_id"], deque()),
                    self.MOVING_WINDOW
                ) < self.STOPPED_SPEED
            )
            if n_stopped / len(vehicles) >= 0.95:
                print(f"{YELLOW}⚠️  TRAFFIC LIGHT GUARD: {n_stopped}/{len(vehicles)} stopped → SKIPPING{RESET}")
                self._validator.update(self._ZONE_ID, False)
                return False, [], vehicles

        print(f"\n{'─'*80}")
        print(f"PAIR SCORING ({len(vehicles) * (len(vehicles)-1) // 2} pairs)")
        print(f"{'─'*80}")

        pair_count = 0
        # ── Per-pair risk scoring ──────────────────────────────────────────────
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                pair_count += 1
                vi, vj = vehicles[i], vehicles[j]

                dx = vi["cx"] - vj["cx"]
                dy = vi["cy"] - vj["cy"]
                centre_dist = float(np.hypot(dx, dy))

                print(f"\n  [{pair_count}] #{vi['track_id']}-#{vj['track_id']} {vi['label']} vs {vj['label']}")
                print(f"       Distance: {centre_dist:.1f}px", end="")

                # Dynamic distance cutoff
                max_speed_i  = max(list(self._speed_histories.get(vi["track_id"], deque([0]))), default=0)
                max_speed_j  = max(list(self._speed_histories.get(vj["track_id"], deque([0]))), default=0)
                from detection.incident_detectors import _box_size
                avg_box_size = (_box_size(vi["box"]) + _box_size(vj["box"])) / 2
                speed_factor = 1 + (max(max_speed_i, max_speed_j) * 3)
                dynamic_cutoff = max(200, avg_box_size * 3)

                print(f" | Cutoff: {dynamic_cutoff:.1f}px", end="")
                if centre_dist > dynamic_cutoff:
                    print(f" {RED}✗ TOO FAR{RESET}")
                    continue
                print(f" {GREEN}✓{RESET}")

                # Motion check
                prev_i   = self._prev_centres.get(vi["track_id"], (vi["cx"], vi["cy"]))
                prev_j   = self._prev_centres.get(vj["track_id"], (vj["cx"], vj["cy"]))
                motion_i = np.array([vi["cx"] - prev_i[0], vi["cy"] - prev_i[1]])
                motion_j = np.array([vj["cx"] - prev_j[0], vj["cy"] - prev_j[1]])

                if np.linalg.norm(motion_i) < 0.01 and np.linalg.norm(motion_j) < 0.01:
                    print(f"       {RED}✗ BOTH STATIC (no motion){RESET}")
                    continue

                # Both stopped + far check
                if self._both_stopped(vi, vj) and centre_dist > 100:
                    print(f"       {RED}✗ BOTH STOPPED + FAR (>100px){RESET}")
                    continue
                if self._both_stopped(vi, vj):
                    print(f"       {YELLOW}⚠️  Both stopped, BUT close (<100px) → CONTINUE{RESET}")

                score, breakdown = self._pair_score(
                    vi, vj, flow_mag, centre_dist, motion_i, motion_j
                )

                print(f"       Score: {BOLD}{score:.3f}{RESET} "
                      f"[bbox={breakdown['bbox']:.2f} dist={breakdown['dist']:.2f} "
                      f"accel={breakdown['accel']:.2f} chaos={breakdown['chaos']:.2f}]")

                # Instant collision check
                instant_hit = self._is_instant_collision(
                    vi, vj,
                    bbox_s      = breakdown["bbox"],
                    chaos_s     = breakdown["chaos"],
                    centre_dist = centre_dist,
                )
                if instant_hit:
                    print(f"       {GREEN}🔥 INSTANT COLLISION DETECTED{RESET}")

                if score < self.SCORE_THRESHOLD:
                    print(f"       {RED}✗ Below threshold ({self.SCORE_THRESHOLD}){RESET}")
                    continue

                print(f"       {GREEN}✓ THRESHOLD PASSED → EVENT ADDED{RESET}")
                events.append(self._make_event(vi, vj, score, breakdown,
                    f"score={score:.2f} bbox={breakdown['bbox']:.2f} "
                    f"dist={breakdown['dist']:.2f} "
                    f"acc={breakdown['accel']:.2f} "
                    f"chaos={breakdown['chaos']:.2f}"
                ))

        print(f"\n{'─'*80}")
        print(f"VALIDATOR CHECK")
        print(f"{'─'*80}")
        print(f"Events detected: {len(events)}")
        print(f"Validator state before: {self._validator.counters.get(self._ZONE_ID, 0)}/({self._validator.required_frames})")
        
        flagged   = len(events) > 0
        confirmed = self._validator.update(self._ZONE_ID, flagged)
        
        print(f"Flagged: {flagged}")
        print(f"Validator state after update: {self._validator.counters.get(self._ZONE_ID, 0)}/({self._validator.required_frames})")
        print(f"Confirmed: {BOLD}{GREEN if confirmed else RED}{confirmed}{RESET}")

        if confirmed:
            self._validator.reset(self._ZONE_ID)
            print(f"{GREEN}✓ COLLISION CONFIRMED AND REPORTED{RESET}")

        return confirmed, events, vehicles

    @staticmethod
    def _rmean_helper(dq: deque, window: int = 0) -> float:
        if not dq:
            return 0.0
        items = list(dq)[-window:] if window > 0 else list(dq)
        return float(np.mean(items)) if items else 0.0

    @staticmethod
    def _make_event(vi, vj, score, breakdown, reason) -> dict:
        return {
            "type":      "road_accident",
            "cx":        (vi["cx"] + vj["cx"]) // 2,
            "cy":        (vi["cy"] + vj["cy"]) // 2,
            "box": (
                min(vi["box"][0], vj["box"][0]),
                min(vi["box"][1], vj["box"][1]),
                max(vi["box"][2], vj["box"][2]),
                max(vi["box"][3], vj["box"][3]),
            ),
            "vehicles":  [vi["label"], vj["label"]],
            "score":     round(score, 3),
            "breakdown": breakdown,
            "reason":    reason,
        }


def run_debug(source):
    """Run video with detailed collision debugging."""
    try:
        source = int(source)
    except (ValueError, TypeError):
        pass

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"❌ Could not open: {source}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"\n{CYAN}═══════════════════════════════════════════════════════════════════════════════{RESET}")
    print(f"{CYAN}AEGIS COLLISION DETECTION DEBUG{RESET}")
    print(f"{CYAN}═══════════════════════════════════════════════════════════════════════════════{RESET}")
    print(f"Source: {source} | FPS: {fps:.1f} | Total frames: {total}")
    print(f"\nControls: Q=quit | SPACE=pause | N=next | S=skip 10\n")

    # Detector with debug accident detector
    print("🔄 Loading models...")
    detector = Detector(acc_debug=True)
    
    # Swap the accident detector with our debug version
    detector.accident_detector = DebugAccidentDetector(confirm_frames=2, debug=True)
    
    frame_num = 0
    paused = False
    collision_frames = []

    while True:
        if not paused:
            ret, frame = cap.read()
            if not ret:
                print(f"\n{GREEN}✓ End of video{RESET}")
                break
            
            frame_num += 1
            
            # Process through debug detector only (skip YOLO pose, fire, etc.)
            annotated = frame.copy()
            h, w = frame.shape[:2]
            
            # Only run accident detection
            confirmed, events, vehicles = detector.accident_detector.detect(frame)
            
            if confirmed or events:
                collision_frames.append(frame_num)
                print(f"\n{BOLD}{GREEN}✓✓✓ COLLISION CONFIRMED AT FRAME {frame_num}{RESET}")
            
            # Draw vehicles on frame
            for v in vehicles:
                x1, y1, x2, y2 = v["box"]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (200, 200, 200), 2)
                cv2.putText(annotated, f"#{v['track_id']}", (x1, y1-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            
            # Draw events
            for ev in events:
                x1, y1, x2, y2 = ev["box"]
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                cv2.putText(annotated, f"COLLISION {ev['score']:.2f}", (x1, y1-15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            
            # HUD
            cv2.putText(annotated, f"Frame {frame_num}/{total}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(annotated, "SPACE=pause | Q=quit | N=next | S=skip10", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 0), 1)
            
            cv2.imshow("Collision Debug", annotated)

        key = cv2.waitKey(33 if not paused else 0) & 0xFF
        if key == ord("q"):
            break
        elif key == ord(" "):
            paused = not paused
            print(f"\n{'PAUSED' if paused else 'RESUMED'}")
        elif key == ord("n"):
            paused = False
        elif key == ord("s"):
            for _ in range(10):
                cap.read()
                frame_num += 1

    cap.release()
    cv2.destroyAllWindows()

    print(f"\n{CYAN}═══════════════════════════════════════════════════════════════════════════════{RESET}")
    print(f"DEBUG SUMMARY")
    print(f"{CYAN}═══════════════════════════════════════════════════════════════════════════════{RESET}")
    print(f"Total frames: {frame_num}")
    print(f"Collision confirmations: {len(collision_frames)}")
    if collision_frames:
        print(f"Confirmed at frames: {collision_frames}")
    else:
        print(f"{RED}❌ NO COLLISIONS DETECTED{RESET}")
        print(f"\nCommon issues to check:")
        print(f"  1. Vehicles not detected at all? → YOLO model issue")
        print(f"  2. Vehicles detected but no pairs qualified? → Distance/motion filters too strict")
        print(f"  3. Pairs scored but below threshold? → Thresholds still too high")
        print(f"  4. Validator never confirms? → Needs consecutive frames")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else 0
    run_debug(source)
