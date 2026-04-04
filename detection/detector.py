"""
The brain of the whole system. Combines all the other modules.

What happens when you call detector.process_frame(frame):

YOLO runs on the frame — gets bounding boxes + 17 keypoints per person
Velocity is tracked — compares each person's current centre to previous frame
Fall detection — checks if shoulder Y ≈ hip Y (person is horizontal):
shoulder_y ≈ hip_y  →  abs(shoulder_y - hip_y) < 40px  →  FALL
FrameValidator — only confirms after 5 consecutive flagged frames
Crowd anomaly — feeds all velocities into CrowdAnomalyDetector
Fire detection — HSV colour thresholding flags orange/red regions
Accident detection — vehicle tracking flags collisions and sudden stops
Annotates the frame — green box = OK, red box + label = FALL, shows frame counter
Returns the annotated frame + list of confirmed incident dicts ready to POST
"""

import cv2
import torch
import numpy as np
from ultralytics import YOLO
from collections import defaultdict

from detection.frame_validator import FrameValidator
from detection.confidence import CrowdAnomalyDetector, blend_confidence
from detection.geo_mapper import pixel_to_latlon
from detection.incident_detectors import FireDetector, AccidentDetector

# ─── CPU optimisation ──────────────────────────────────────────────────────
torch.set_num_threads(4)

# ─── Keypoint indices (COCO format used by YOLOv8-pose) ───────────────────
KP_LEFT_SHOULDER  = 5
KP_RIGHT_SHOULDER = 6
KP_LEFT_HIP       = 11
KP_RIGHT_HIP      = 12

# Fall detection tuning
# ─────────────────────────────────────────────────────────────────────────────
# RELATIVE threshold: shoulder-to-hip vertical span must be less than this
# fraction of the person's bounding-box height to count as "fallen".
#
# A standing person: shoulder-to-hip ≈ 35–45% of their bbox height.
# A fallen person:   shoulder-to-hip compresses to < 20% of bbox height
#                    (because they are lying sideways/flat).
#
# Using a relative value instead of absolute pixels means the threshold
# scales correctly for both close-up and far-away detections.
#
FALL_RELATIVE_THRESHOLD = 0.22   # tune: lower → less sensitive, higher → more sensitive

# Minimum keypoint confidence to trust a shoulder/hip keypoint.
# YOLOv8-pose attaches a confidence per keypoint; low scores mean the
# keypoint was estimated rather than clearly visible.
KP_CONF_MIN = 0.35

# Severity scores per incident type (used in the backend payload)
SEVERITY_MAP = {
    "fallen_person": 7.0,
    "fire":          9.0,
    "road_accident": 8.0,
}


class Detector:
    """
    Wraps the full AI pipeline:
      1. YOLOv8-pose  — people detection + fall detection
      2. FrameValidator — 5-frame persistence (fall)
      3. IsolationForest — crowd anomaly detection
      4. FireDetector  — HSV colour-space fire detection
      5. AccidentDetector — vehicle tracking, collision + sudden-stop detection
      6. Geo-mapping pixel → lat/lng zone
    """

    def __init__(
        self,
        model_path: str = "yolov8n-pose.pt",
        imgsz: int = 320,
        confirm_frames: int = 5,
        camera_id: str = "CAM-01",
        acc_debug: bool = False,
    ):
        print(f"🔄 Loading pose model: {model_path}")
        self.model  = YOLO(model_path)
        self.imgsz  = imgsz
        self.camera_id = camera_id

        self.validator        = FrameValidator(required_frames=confirm_frames)
        self.anomaly_detector = CrowdAnomalyDetector()

        # Fire + accident sub-detectors
        self.fire_detector     = FireDetector(confirm_frames=confirm_frames)
        self.accident_detector = AccidentDetector(
            confirm_frames=2, debug=acc_debug
        )

        # Per-person previous bounding-box centres for velocity tracking
        self._prev_centres: dict[int, tuple[float, float]] = {}
        self._incident_counter = 0

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _next_incident_id(self) -> str:
        self._incident_counter += 1
        return f"INC-{self._incident_counter:04d}"

    def _make_incident(self, inc_type: str, cx: float, cy: float,
                       yolo_conf: float, anomaly_score: float,
                       people_in_frame: int) -> dict:
        """Build a complete incident payload dict from detected values."""
        lat, lng, zone = pixel_to_latlon(cx, cy)
        detect_confidence = blend_confidence(
            yolo_conf=yolo_conf,
            zone_accident_frequency=zone.accident_frequency,
            anomaly_score=anomaly_score,
        )
        return {
            "id":                      self._next_incident_id(),
            "zone_id":                 zone.zone_id,
            "zone_accident_frequency": zone.accident_frequency,
            "type":                    inc_type,
            "severity":                SEVERITY_MAP.get(inc_type, 7.0),
            "camera_id":               self.camera_id,
            "camera_coverage":         zone.camera_coverage,
            "people_in_frame":         people_in_frame,
            "lat":                     lat,
            "lng":                     lng,
            "detect_confidence":       detect_confidence,
        }

    # ── Main entry point ───────────────────────────────────────────────────────

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, list[dict]]:
        """
        Process a single BGR frame through all detectors.
        Returns (annotated_frame, list_of_confirmed_incident_dicts).
        """
        h, w        = frame.shape[:2]
        annotated   = frame.copy()
        incidents: list[dict] = []

        # ══════════════════════════════════════════════════════════════════════
        #  1. POSE MODEL — Fall detection
        # ══════════════════════════════════════════════════════════════════════
        results   = self.model(frame, imgsz=self.imgsz, verbose=False)
        res       = results[0]
        boxes     = res.boxes
        keypoints = res.keypoints

        people_in_frame = len(boxes) if boxes is not None else 0
        velocities: list[tuple[float, float]] = []

        pending_falls = []   # fall incidents waiting for anomaly score

        for person_id, box in enumerate(boxes):
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cx        = (x1 + x2) / 2
            cy        = (y1 + y2) / 2
            yolo_conf = float(box.conf[0])

            # Velocity tracking
            if person_id in self._prev_centres:
                px, py = self._prev_centres[person_id]
                vx, vy = cx - px, cy - py
            else:
                vx, vy = 0.0, 0.0
            self._prev_centres[person_id] = (cx, cy)
            velocities.append((vx, vy))

            # ── Fall detection via keypoints (relative threshold) ──────────
            is_fallen = False
            if keypoints is not None and person_id < len(keypoints.xy):
                kps      = keypoints.xy[person_id]    # shape (17, 2)
                kps_conf = (
                    keypoints.conf[person_id].tolist()
                    if keypoints.conf is not None
                    else [1.0] * 17
                )

                if kps.shape[0] >= 13:
                    # Only use keypoints with sufficient confidence
                    ls_conf = kps_conf[KP_LEFT_SHOULDER]
                    rs_conf = kps_conf[KP_RIGHT_SHOULDER]
                    lh_conf = kps_conf[KP_LEFT_HIP]
                    rh_conf = kps_conf[KP_RIGHT_HIP]

                    if min(ls_conf, rs_conf, lh_conf, rh_conf) >= KP_CONF_MIN:
                        shoulder_y = float(
                            (kps[KP_LEFT_SHOULDER][1] + kps[KP_RIGHT_SHOULDER][1]) / 2
                        )
                        hip_y = float(
                            (kps[KP_LEFT_HIP][1] + kps[KP_RIGHT_HIP][1]) / 2
                        )
                        bbox_height = max(y2 - y1, 1)   # avoid div-by-zero
                        dy_relative = abs(shoulder_y - hip_y) / bbox_height

                        # Person is fallen if shoulder-hip span is tiny
                        # relative to their own bounding box height
                        if dy_relative < FALL_RELATIVE_THRESHOLD:
                            is_fallen = True

            # Frame validation
            confirmed = self.validator.update(person_id, is_fallen)

            # Annotate
            color = (0, 0, 255) if is_fallen else (0, 255, 0)
            label = f"FALL! ({self.validator.get_count(person_id)}/5)" if is_fallen else "OK"
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

            if confirmed:
                self.validator.reset(person_id)
                pending_falls.append((cx, cy, yolo_conf, people_in_frame))

        # ══════════════════════════════════════════════════════════════════════
        #  2. CROWD ANOMALY
        # ══════════════════════════════════════════════════════════════════════
        density       = people_in_frame / max(w * h / 10000, 1)
        anomaly_score = self.anomaly_detector.update(velocities, density)

        cv2.putText(
            annotated,
            f"Crowd anomaly: {anomaly_score:.2f}   People: {people_in_frame}",
            (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2,
        )

        # Finalise fall incidents now that we have anomaly_score
        for cx, cy, yolo_conf, pip in pending_falls:
            incidents.append(self._make_incident(
                "fallen_person", cx, cy, yolo_conf, anomaly_score, pip
            ))

        # ══════════════════════════════════════════════════════════════════════
        #  3. FIRE DETECTION
        # ══════════════════════════════════════════════════════════════════════
        fire_confirmed, fire_events = self.fire_detector.detect(frame)

        for ev in fire_events:
            x1, y1, x2, y2 = ev["box"]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 100, 255), 2)
            progress = self.fire_detector._validator.get_count(0)
            cv2.putText(
                annotated,
                f"FIRE? ({progress}/8)  area={ev['area']:.0f}px",
                (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 100, 255), 2,
            )

        if fire_confirmed and fire_events:
            ev = fire_events[0]   # use first (largest could be added later)
            incidents.append(self._make_incident(
                "fire", ev["cx"], ev["cy"],
                yolo_conf=0.75,       # HSV doesn't give a model score; use fixed value
                anomaly_score=anomaly_score,
                people_in_frame=people_in_frame,
            ))
            cv2.putText(annotated, "🔥 FIRE CONFIRMED", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 60, 255), 2)

        # ══════════════════════════════════════════════════════════════════════
        #  4. ACCIDENT DETECTION
        # ══════════════════════════════════════════════════════════════════════
        acc_confirmed, acc_events, vehicles = self.accident_detector.detect(frame)

        # Draw all tracked vehicles in grey with their stable track ID
        for v in vehicles:
            x1, y1, x2, y2 = v["box"]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (180, 180, 180), 1)
            cv2.putText(
                annotated,
                f"{v['label']} #{v['track_id']} {v['conf']:.2f}",
                (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1,
            )

        # Draw accident events in red
        for ev in acc_events:
            x1, y1, x2, y2 = ev["box"]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
            progress = self.accident_detector._validator.get_count(0)
            cv2.putText(
                annotated,
                f"ACCIDENT? ({progress}/8) {ev['reason']}",
                (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2,
            )

        if acc_confirmed and acc_events:
            ev = acc_events[0]
            incidents.append(self._make_incident(
                "road_accident", ev["cx"], ev["cy"],
                yolo_conf=0.80,
                anomaly_score=anomaly_score,
                people_in_frame=people_in_frame,
            ))
            cv2.putText(annotated, "ACCIDENT CONFIRMED", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 200), 2)

        return annotated, incidents
