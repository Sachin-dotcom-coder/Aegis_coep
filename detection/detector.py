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
import requests
import datetime
import os
from ultralytics import YOLO
from collections import defaultdict
from dotenv import load_dotenv

from detection.frame_validator import FrameValidator
from detection.confidence import CrowdAnomalyDetector, blend_confidence
from detection.geo_mapper import pixel_to_latlon
from detection.incident_detectors import FireDetector, AccidentDetector, ImpactFlashDetector, SceneCutDetector

# ─── Load environment variables ────────────────────────────────────────────
load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

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
# Base severity values - will be dynamically adjusted based on area and zone frequency
SEVERITY_MAP = {
    "fallen_person": 6.0,   # Base severity
    "fire":          8.5,   # Base severity (fire is serious)
    "road_accident": 7.5,   # Base severity
    "gun_fired":     9.5,   # Base severity (weapon fire is critical)
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
        self.confirm_frames = confirm_frames
        self.acc_debug = acc_debug


        self.validator        = FrameValidator(required_frames=confirm_frames)
        self.anomaly_detector = CrowdAnomalyDetector()

        # Fire + accident sub-detectors
        self.fire_detector     = FireDetector(confirm_frames=confirm_frames)
        self.accident_detector = AccidentDetector(
            confirm_frames=1, debug=acc_debug
        )
        self.impact_detector   = ImpactFlashDetector(confirm_frames=1)
        self.scene_cut_detector = SceneCutDetector()

        self._prev_centres: dict[int, tuple[float, float]] = {}
        self._frames_since_seen: dict[int, int] = {}
        self.FORGET_AFTER_FRAMES = 10
        self._incident_cooldown: dict[int, int] = {}
        self.COOLDOWN_FRAMES = 150  # 5 seconds at 30fps
        # Add a global cooldown per incident type to prevent infinite API spam
        self._type_cooldown: dict[str, int] = {
            "fire": 0,
            "road_accident": 0,
            "gun_fired": 0
        }
        self._incident_counter = 0
        self._frame_count = 0
        self._scene_cut_count = 0

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _match_person_id(self, cx: float, cy: float) -> int:
        """
        Match current detection to the closest person from the last frame.
        Returns a stable ID that persists across frames.
        """
        MAX_DISTANCE = 80  # pixels

        best_id   = None
        best_dist = float('inf')

        for pid, (px, py) in self._prev_centres.items():
            dist = ((cx - px)**2 + (cy - py)**2) ** 0.5
            if dist < best_dist and dist < MAX_DISTANCE:
                best_dist = dist
                best_id   = pid

        if best_id is None:
            best_id = max(self._prev_centres.keys(), default=-1) + 1

        return best_id

    def _cleanup_lost_persons(self, active_ids: set):
        """Remove people who haven't been seen recently."""
        all_ids = list(self._prev_centres.keys())
        for pid in all_ids:
            if pid not in active_ids:
                self._frames_since_seen[pid] = self._frames_since_seen.get(pid, 0) + 1
                if self._frames_since_seen[pid] > self.FORGET_AFTER_FRAMES:
                    self._prev_centres.pop(pid, None)
                    self._frames_since_seen.pop(pid, None)
                    self.validator.reset(pid)
            else:
                self._frames_since_seen[pid] = 0



    def _next_incident_id(self) -> str:
        self._incident_counter += 1
        return f"INC-{self._incident_counter:04d}"

    def _calculate_severity(
        self, inc_type: str, event_area: float,
        zone_frequency: float, people_in_frame: int,
        rotation_detected: bool = False, vehicle_speeds: list = None
    ) -> float:
        """
        Calculate dynamic severity based on:
        1. Incident type (base severity)
        2. Event area/size (larger = more severe)
        3. Zone frequency (incidents in high-crime areas = more severe)
        4. People in frame (crowded areas = more severe)
        5. Vehicle rotation (rotated car = impact = more severe)
        6. Vehicle speed (high-speed collision = more severe)
        
        Returns float between 1.0-10.0
        """
        base_severity = SEVERITY_MAP.get(inc_type, 6.0)
        
        # ── AREA FACTOR (normalize to 0-1) ──────────────────────────────────
        # For fire: area in pixels (larger area = higher severity)
        # For accidents: bbox area (larger accident zone = higher severity)
        # For falls: area factor based on people count (more people = more severe)
        area_factor = 1.0
        
        if inc_type == "fire":
            # Fire area: 5000-50000 pixels is normal range
            # Smaller fire = less severe, larger fire = more severe
            area_factor = min(1.0, event_area / 30000.0)
            area_factor = 0.5 + (area_factor * 0.5)  # Scale: 0.5-1.0
            
        elif inc_type == "road_accident":
            # Accident area: 2000-15000 pixels typical
            # Larger collision area (more damage) = higher severity
            area_factor = min(1.0, event_area / 20000.0)
            area_factor = 0.6 + (area_factor * 0.4)  # Scale: 0.6-1.0
            
        elif inc_type == "fallen_person":
            # For falls: factor in number of people and crowd density
            # Single fall = less severe, multiple people/crowded = more severe
            people_factor = min(1.0, people_in_frame / 10.0)  # 10+ people = max severity
            area_factor = 0.7 + (people_factor * 0.3)  # Scale: 0.7-1.0
            
        elif inc_type == "gun_fired":
            # Gun fired events are already critical, area less important
            # But if in crowded area = significantly more severe
            people_factor = min(1.0, people_in_frame / 5.0)  # 5+ people in frame
            area_factor = 0.8 + (people_factor * 0.2)  # Scale: 0.8-1.0
        
        # ── ZONE FREQUENCY FACTOR (0-1) ────────────────────────────────────
        # Higher crime zones = higher severity for same incident
        # zone_frequency typically 0.0-1.0 (accident rate in zone)
        zone_factor = 1.0 + (zone_frequency * 0.4)  # Scale: 1.0-1.4
        
        # ── CROWD DENSITY FACTOR ────────────────────────────────────────────
        # Same incident in crowded area is more severe
        crowd_factor = 1.0 + min(0.2, people_in_frame * 0.02)  # Scale: 1.0-1.2
        
        # ── VEHICLE ROTATION FACTOR (for road accidents) ────────────────────
        # Vehicle rotation during impact = significant damage indicator
        rotation_factor = 1.0
        if inc_type == "road_accident" and rotation_detected:
            rotation_factor = 1.4  # +40% severity boost for rotated vehicles
        
        # ── HIGH SPEED FACTOR (for road accidents) ─────────────────────────
        # High-speed collisions are more severe than low-speed
        speed_factor = 1.0
        if inc_type == "road_accident" and vehicle_speeds:
            # Find max speed from involved vehicles
            max_speed = max(vehicle_speeds) if vehicle_speeds else 0.0
            # Normalize speed: 0.1-0.5 is low, 0.5+ is high
            if max_speed > 0.5:
                speed_boost = min(0.5, (max_speed - 0.5) * 0.5)  # Up to +0.25 (25%)
                speed_factor = 1.0 + speed_boost  # Scale: 1.0-1.25
                print(f"    ⚠️  HIGH-SPEED collision detected (max_speed={max_speed:.2f}) → +{speed_boost*100:.0f}% severity")
        
        # ── FINAL CALCULATION ──────────────────────────────────────────────
        # severity = base * area_factor * zone_factor * crowd_factor * rotation_factor * speed_factor
        calculated_severity = (base_severity * area_factor * zone_factor * 
                              crowd_factor * rotation_factor * speed_factor)
        
        # Clamp to 1.0-10.0 range
        return float(np.clip(calculated_severity, 1.0, 10.0))

    def _make_incident(self, inc_type: str, cx: float, cy: float,
                       yolo_conf: float, anomaly_score: float,
                       people_in_frame: int, event_area: float = 1000.0,
                       rotation_detected: bool = False, vehicle_speeds: list = None) -> dict:
        """Build a complete incident payload dict from detected values."""
        lat, lng, zone = pixel_to_latlon(cx, cy, camera_id=self.camera_id)
        detect_confidence = blend_confidence(
            yolo_conf=yolo_conf,
            zone_accident_frequency=zone.accident_frequency,
            anomaly_score=anomaly_score,
        )
        
        # Calculate dynamic severity based on area, zone, rotation, and speed
        severity = self._calculate_severity(
            inc_type=inc_type,
            event_area=event_area,
            zone_frequency=zone.accident_frequency,
            people_in_frame=people_in_frame,
            rotation_detected=rotation_detected,
            vehicle_speeds=vehicle_speeds,
        )
        
        return {
            "id":                      self._next_incident_id(),
            "zone_id":                 zone.zone_id,
            "zone_accident_frequency": zone.accident_frequency,
            "type":                    inc_type,
            "severity":                round(severity, 2),  # Round to 2 decimals
            "camera_id":               self.camera_id,
            "camera_coverage":         zone.camera_coverage,
            "people_in_frame":         people_in_frame,
            "lat":                     lat,
            "lng":                     lng,
            "detect_confidence":       detect_confidence,
        }

    # ── Main entry point ───────────────────────────────────────────────────────

    def post_incident_to_backend(self, incident: dict) -> bool:
        """
        POST an incident to the FastAPI backend for database storage and drone dispatch.
        
        Args:
            incident: Incident dict with id, type, severity, lat, lng, etc.
            
        Returns:
            bool: True if successful, False if failed
        """
        # Add timestamp if not already present
        if "timestamp" not in incident:
            incident["timestamp"] = datetime.datetime.utcnow().isoformat()
        
        try:
            print(f"\n📡 Posting incident to backend: {incident['id']} ({incident['type']}) "
                  f"severity={incident['severity']} at ({incident['lat']:.4f}, {incident['lng']:.4f})")
            
            resp = requests.post(
                f"{BACKEND_URL}/incidents/",
                json=incident,
                timeout=5
            )
            resp.raise_for_status()
            data = resp.json()
            
            print(f"   ✅ Backend response: {data}")
            return True
            
        except requests.exceptions.ConnectionError as e:
            print(f"   ⚠️  Could not connect to backend: {BACKEND_URL}")
            print(f"      (Make sure FastAPI is running) Error: {e}")
            return False
        except requests.exceptions.Timeout:
            print(f"   ⚠️  Backend request timed out (timeout=5s)")
            return False
        except requests.exceptions.HTTPError as e:
            print(f"   ⚠️  Backend returned error: {e.response.status_code}")
            try:
                print(f"      Response: {e.response.text}")
            except:
                pass
            return False
        except Exception as e:
            print(f"   ⚠️  Unexpected error posting to backend: {e}")
            return False

    def process_frame(self, frame: np.ndarray) -> tuple[np.ndarray, list[dict]]:
        """
        Process a single BGR frame through all detectors.
        Returns (annotated_frame, list_of_confirmed_incident_dicts).
        """
        self._frame_count += 1
        h, w        = frame.shape[:2]
        annotated   = frame.copy()

        # ── Scene cut detection (resets tracking on clip transitions) ────────
        if self.scene_cut_detector.update(frame):
            self._scene_cut_count += 1
            # SOFT RESET: Clear frame-to-frame buffers but KEEP track histories
            self.accident_detector.soft_reset()
            self.impact_detector.reset()
            self.fire_detector._validator.reset(0)
            
            # Show the cut message but DON'T return early - let YOLO/tracking run
            # so that IDs don't disappear and reappear (flickering fixed!)
            print(f"[SCENE CUT #{self._scene_cut_count}] Frame {self._frame_count}")
            cv2.putText(annotated, "SCENE CUT DETECTED (SOFT RESET)", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # Skip heavy processing for THIS frame to avoid false positives
            return annotated, []

        incidents: list[dict] = []

        # Decrement global type cooldowns
        for t in self._type_cooldown:
            if self._type_cooldown[t] > 0:
                self._type_cooldown[t] -= 1

        # ══════════════════════════════════════════════════════════════════════
        #  1. POSE MODEL — Fall detection (Omitted for brevity - already has per-person cooldown)
        # ══════════════════════════════════════════════════════════════════════
        results   = self.model(frame, imgsz=self.imgsz, verbose=False)
        res       = results[0]
        boxes     = res.boxes
        keypoints = res.keypoints

        people_in_frame = len(boxes) if boxes is not None else 0
        velocities: list[tuple[float, float]] = []
        pending_falls = []   
        active_ids = set()

        if people_in_frame > 0:
            for idx, box in enumerate(boxes):
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cx        = (x1 + x2) / 2
                cy        = (y1 + y2) / 2
                person_id = self._match_person_id(cx, cy)
                active_ids.add(person_id)
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
                if keypoints is not None and idx < len(keypoints.xy):
                    kps      = keypoints.xy[idx]    # shape (17, 2)
                    kps_conf = (
                        keypoints.conf[idx].tolist()
                        if keypoints.conf is not None
                        else [1.0] * 17
                    )

                    if kps.shape[0] >= 13:
                        ls_conf = kps_conf[KP_LEFT_SHOULDER]
                        rs_conf = kps_conf[KP_RIGHT_SHOULDER]
                        lh_conf = kps_conf[KP_LEFT_HIP]
                        rh_conf = kps_conf[KP_RIGHT_HIP]

                        best_shoulder_conf = max(ls_conf, rs_conf)
                        best_hip_conf      = max(lh_conf, rh_conf)

                        if best_shoulder_conf >= KP_CONF_MIN and best_hip_conf >= KP_CONF_MIN:
                            shoulder_y = (
                                float(kps[KP_LEFT_SHOULDER][1])  if ls_conf >= rs_conf
                                else float(kps[KP_RIGHT_SHOULDER][1])
                            )
                            hip_y = (
                                float(kps[KP_LEFT_HIP][1])  if lh_conf >= rh_conf
                                else float(kps[KP_RIGHT_HIP][1])
                            )
                            bbox_height = max(y2 - y1, 1)   
                            dy_relative = abs(shoulder_y - hip_y) / bbox_height

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
                    cooldown_remaining = self._incident_cooldown.get(person_id, 0)
                    if cooldown_remaining == 0:
                        self.validator.reset(person_id)
                        # Store person bbox area for severity calculation
                        bbox_area = (x2 - x1) * (y2 - y1)
                        pending_falls.append((cx, cy, yolo_conf, people_in_frame, bbox_area))
                        self._incident_cooldown[person_id] = self.COOLDOWN_FRAMES

        self._cleanup_lost_persons(active_ids)
        for pid in list(self._incident_cooldown):
            self._incident_cooldown[pid] -= 1
            if self._incident_cooldown[pid] <= 0:
                del self._incident_cooldown[pid]

        # ══════════════════════════════════════════════════════════════════════
        #  2. CROWD ANOMALY
        # ══════════════════════════════════════════════════════════════════════
        density       = people_in_frame / max(w * h / 10000, 1)
        anomaly_score = self.anomaly_detector.update(velocities, density)

        if people_in_frame > 0:
            cv2.putText(
                annotated,
                f"Crowd anomaly: {anomaly_score:.2f}   People: {people_in_frame}",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2,
            )
        else:
            cv2.putText(annotated, "No people detected", (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        # Finalise fall incidents now that we have anomaly_score
        for cx, cy, yolo_conf, pip, bbox_area in pending_falls:
            incidents.append(self._make_incident(
                "fallen_person", cx, cy, yolo_conf, anomaly_score, pip,
                event_area=bbox_area
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
            fire_area = ev.get("area", 1000)
            fire_conf = min(0.5 + (fire_area / 20000), 0.95)
            
            cv2.putText(annotated, "🔥 FIRE CONFIRMED", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 60, 255), 2)
                        
            if self._type_cooldown["fire"] <= 0:
                incidents.append(self._make_incident(
                    "fire", ev["cx"], ev["cy"],
                    yolo_conf=fire_conf,       # dynamic score based on fire area
                    anomaly_score=anomaly_score,
                    people_in_frame=people_in_frame,
                    event_area=fire_area,  # Pass fire area for severity calculation
                ))
                self._type_cooldown["fire"] = 150  # 5 seconds cooldown

        # ══════════════════════════════════════════════════════════════════════
        #  4. ACCIDENT DETECTION
        # ══════════════════════════════════════════════════════════════════════
        acc_confirmed, acc_events, vehicles = self.accident_detector.detect(frame, frame_id=self._frame_count)

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
            # Calculate accident bbox area for severity
            x1, y1, x2, y2 = ev["box"]
            accident_area = (x2 - x1) * (y2 - y1)
            
            # Check if any vehicle in the accident was rotated (impact indicator)
            rotation_detected = False
            vehicle_speeds = []
            for v in vehicles:
                if v.get("rotated", False):
                    rotation_detected = True
                    print(f"    🔄 Vehicle #{v['track_id']} ROTATED during collision → SEVERE impact")
                vehicle_speeds.append(v.get("speed", 0.0))
            
            if rotation_detected:
                print(f"    🚨 ROTATION DETECTED - Boosting severity +40%")
            
            cv2.putText(annotated, "ACCIDENT CONFIRMED", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 200), 2)
                        
            if self._type_cooldown["road_accident"] <= 0:
                incidents.append(self._make_incident(
                    "road_accident", ev["cx"], ev["cy"],
                    yolo_conf=0.80,
                    anomaly_score=anomaly_score,
                    people_in_frame=people_in_frame,
                    event_area=accident_area,
                    rotation_detected=rotation_detected,
                    vehicle_speeds=vehicle_speeds,
                ))
                self._type_cooldown["road_accident"] = 150 # 5 sec cooldown

        # ══════════════════════════════════════════════════════════════════════
        #  5. IMPACT FLASH DETECTION (catches dust/smoke explosions)
        # ══════════════════════════════════════════════════════════════════════
        flash_confirmed, flash_event = self.impact_detector.detect(frame)

        if flash_confirmed and flash_event:
            # Only fire if vehicles were recently seen (avoid false alarms on cuts)
            if len(self._prev_centres) >= 1:
                # Calculate flash area from bbox
                x1, y1, x2, y2 = flash_event.get("box", (0, 0, w, h))
                flash_area = (x2 - x1) * (y2 - y1)
                
                # Check if any vehicle has rotated (flash near rotated vehicle = high impact)
                rotation_detected = False
                vehicle_speeds = []
                for v in vehicles:
                    if v.get("rotated", False):
                        rotation_detected = True
                    vehicle_speeds.append(v.get("speed", 0.0))
                
                cv2.putText(annotated, "IMPACT FLASH DETECTED", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                            
                if self._type_cooldown["road_accident"] <= 0:
                    incidents.append(self._make_incident(
                        "road_accident",
                        flash_event["cx"], flash_event["cy"],
                        yolo_conf       = 0.82,
                        anomaly_score   = anomaly_score,
                        people_in_frame = people_in_frame,
                        event_area      = flash_area,
                        rotation_detected = rotation_detected,
                        vehicle_speeds = vehicle_speeds,
                    ))
                    self._type_cooldown["road_accident"] = 150 # 5 sec cooldown

        # ══════════════════════════════════════════════════════════════════════
        #  POST INCIDENTS TO BACKEND DATABASE
        # ══════════════════════════════════════════════════════════════════════
        if len(incidents) > 0:
            print(f"\n{'='*70}")
            print(f"🔔 {len(incidents)} incident(s) detected in frame #{self._frame_count}")
            print(f"{'='*70}")
            
            for incident in incidents:
                self.post_incident_to_backend(incident)

        return annotated, incidents
