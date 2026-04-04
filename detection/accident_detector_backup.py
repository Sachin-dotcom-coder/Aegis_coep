"""
PHYSICS-BASED ACCIDENT DETECTOR (Previous version - restored)
This is the advanced collision detection system using:
- Optical flow (chaos signal)
- Speed histories & acceleration
- Proximity bonuses
- Direction analysis
"""

import cv2
import numpy as np
import torch
from collections import deque
from ultralytics import YOLO

from detection.frame_validator import FrameValidator
from detection.incident_detectors import OpticalFlowAnalyzer

_VEHICLE_CLASSES    = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
_TRAFFIC_LIGHT_RATIO = 0.95


class AccidentDetector:
    """
    Detects road accidents using a 4-signal weighted risk score per vehicle pair.
    Signals: bbox overlap, distance risk, deceleration, optical flow chaos.
    """

    W_BBOX  = 0.30
    W_DIST  = 0.40
    W_ACCEL = 0.00
    W_CHAOS = 0.30

    SCORE_THRESHOLD        = 0.32   # Lowered threshold for single-frame catches
    SAFE_DIST_FACTOR       = 1.5
    MAX_ACCEL_SPEED        = 0.3
    MAX_CHAOS_PX           = 2.0
    DEDUP_IOU_THRESH       = 0.85
    STOPPED_SPEED          = 0.05
    MOVING_WINDOW          = 8
    SPEED_HISTORY          = 25
    INSTANT_COLLISION_BBOX = 0.15
    INSTANT_COLLISION_CHAOS= 0.15
    INSTANT_SPEED_DROP     = 0.5

    def __init__(
        self,
        confirm_frames: int = 1,
        model_path: str     = "yolov8m.pt",
        debug: bool         = False,
    ):
        print(f"🔄 Loading vehicle detection model: {model_path}")
        self._model         = YOLO(model_path)
        self._validator     = FrameValidator(required_frames=confirm_frames)
        self._flow_analyzer = OpticalFlowAnalyzer()
        self._debug         = debug
        self._ZONE_ID       = 0
        self._confirm_frames = confirm_frames

        # Keyed by ByteTrack ID
        self._prev_centres:    dict[int, tuple[float, float]] = {}
        self._speed_histories: dict[int, deque]               = {}
        self._prev_speeds:     dict[int, float]               = {}

    def soft_reset(self):
        """Soft reset after scene cut."""
        self._validator     = FrameValidator(required_frames=self._confirm_frames)
        self._flow_analyzer.reset()

    def full_reset(self):
        """Hard reset - clears everything."""
        self.soft_reset()
        self._prev_centres.clear()
        self._speed_histories.clear()
        self._prev_speeds.clear()

    def detect(self, frame: np.ndarray) -> tuple[bool, list[dict], list[dict]]:
        """Main detection method."""
        results  = self._model.track(
            frame, imgsz=416, persist=True, verbose=False
        )
        vehicles = self._extract_vehicles(results[0].boxes)
        vehicles = self._dedup_vehicles(vehicles)

        flow_mag = self._flow_analyzer.update(frame)
        events: list[dict] = []

        # ── Traffic-light guard ────────────────────────────────────────────────
        if len(vehicles) >= 3:
            n_stopped = sum(
                1 for v in vehicles
                if _rmean(
                    self._speed_histories.get(v["track_id"], deque()),
                    self.MOVING_WINDOW
                ) < self.STOPPED_SPEED
            )
            if n_stopped / len(vehicles) >= _TRAFFIC_LIGHT_RATIO:
                self._validator.update(self._ZONE_ID, False)
                return False, [], vehicles

        # ── Per-pair risk scoring ──────────────────────────────────────────────
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                vi, vj = vehicles[i], vehicles[j]

                dx = vi["cx"] - vj["cx"]
                dy = vi["cy"] - vj["cy"]
                centre_dist = float(np.hypot(dx, dy))

                # Dynamic distance cutoff — scales with vehicle speed
                max_speed_i  = max(list(self._speed_histories.get(vi["track_id"], deque([0]))), default=0)
                max_speed_j  = max(list(self._speed_histories.get(vj["track_id"], deque([0]))), default=0)
                avg_box_size = (_box_size(vi["box"]) + _box_size(vj["box"])) / 2
                speed_factor = 1 + (max(max_speed_i, max_speed_j) * 3)
                dynamic_cutoff = max(200, avg_box_size * 3)

                if centre_dist > dynamic_cutoff:
                    continue

                # Direction filter — skip both-stationary pairs
                prev_i   = self._prev_centres.get(vi["track_id"], (vi["cx"], vi["cy"]))
                prev_j   = self._prev_centres.get(vj["track_id"], (vj["cx"], vj["cy"]))
                motion_i = np.array([vi["cx"] - prev_i[0], vi["cy"] - prev_i[1]])
                motion_j = np.array([vj["cx"] - prev_j[0], vj["cy"] - prev_j[1]])

                if np.linalg.norm(motion_i) < 0.01 and np.linalg.norm(motion_j) < 0.01:
                    continue

                if self._both_stopped(vi, vj) and centre_dist > 100:
                    continue

                score, breakdown = self._pair_score(
                    vi, vj, flow_mag, centre_dist, motion_i, motion_j
                )

                # Instant collision bypass
                instant_hit = self._is_instant_collision(
                    vi, vj,
                    bbox_s      = breakdown["bbox"],
                    chaos_s     = breakdown["chaos"],
                    centre_dist = centre_dist,
                )

                if instant_hit:
                    score = max(score, 0.85)
                    events.append(self._make_event(vi, vj, score, breakdown,
                                                   "INSTANT COLLISION DETECTED"))
                    continue

                if self._debug:
                    print(
                        f"[Acc] #{vi['track_id']} {vi['label']} vs "
                        f"#{vj['track_id']} {vj['label']} "
                        f"score={score:.3f} "
                        f"(bbox={breakdown['bbox']:.2f} "
                        f"dist={breakdown['dist']:.2f} "
                        f"accel={breakdown['accel']:.2f} "
                        f"chaos={breakdown['chaos']:.2f})"
                    )

                if score < self.SCORE_THRESHOLD:
                    continue

                events.append(self._make_event(vi, vj, score, breakdown,
                    f"score={score:.2f} bbox={breakdown['bbox']:.2f} "
                    f"dist={breakdown['dist']:.2f} "
                    f"acc={breakdown['accel']:.2f} "
                    f"chaos={breakdown['chaos']:.2f}"
                ))

        flagged   = len(events) > 0
        confirmed = self._validator.update(self._ZONE_ID, flagged)
        if confirmed:
            self._validator.reset(self._ZONE_ID)

        return confirmed, events, vehicles

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

    def _is_instant_collision(self, vi, vj, bbox_s, chaos_s, centre_dist) -> bool:
        if centre_dist < 50:
            return True
        if bbox_s >= self.INSTANT_COLLISION_BBOX:
            return True
        if chaos_s >= self.INSTANT_COLLISION_CHAOS and centre_dist < 150:
            return True

        prev_i = list(self._speed_histories.get(vi["track_id"], [0]))
        prev_j = list(self._speed_histories.get(vj["track_id"], [0]))
        
        if len(prev_i) >= 2:
            drop_i = prev_i[-2] - vi["speed"]
            if drop_i > self.INSTANT_SPEED_DROP:
                return True
                
        if len(prev_j) >= 2:
            drop_j = prev_j[-2] - vj["speed"]
            if drop_j > self.INSTANT_SPEED_DROP:
                return True
                
        return False

    def _pair_score(self, vi, vj, flow_mag, centre_dist, motion_i, motion_j):
        w_i = vi["box"][2] - vi["box"][0]
        h_i = vi["box"][3] - vi["box"][1]
        w_j = vj["box"][2] - vj["box"][0]
        h_j = vj["box"][3] - vj["box"][1]

        w_sum_half = (w_i + w_j) / 2.0
        h_sum_half = (h_i + h_j) / 2.0

        dx_abs   = abs(vi["cx"] - vj["cx"])
        dy_abs   = abs(vi["cy"] - vj["cy"])
        overlap_x = w_sum_half - dx_abs
        overlap_y = h_sum_half - dy_abs
        margin_x  = w_sum_half * 0.05
        margin_y  = h_sum_half * 0.05

        if overlap_x > -margin_x and overlap_y > -margin_y:
            pct_x  = min(1.0, max(0.0, overlap_x / w_sum_half)) if w_sum_half > 0 else 0
            pct_y  = min(1.0, max(0.0, overlap_y / h_sum_half)) if h_sum_half > 0 else 0
            bbox_s = (pct_x + pct_y) / 2.0
            if bbox_s == 0:
                bbox_s = 0.15
        else:
            bbox_s = 0.0

        avg_size  = (_box_size(vi["box"]) + _box_size(vj["box"])) / 2.0
        safe_dist = float(np.clip(avg_size * self.SAFE_DIST_FACTOR, 50, 200))
        dist_s    = float(np.clip(1.0 - centre_dist / safe_dist, 0.0, 1.0))

        if centre_dist < 150:
            dist_s = min(dist_s * 1.5, 1.0)

        mean_speed_i       = _rmean(self._speed_histories.get(vi["track_id"], deque()), self.MOVING_WINDOW)
        mean_speed_j       = _rmean(self._speed_histories.get(vj["track_id"], deque()), self.MOVING_WINDOW)
        at_least_one_moving = mean_speed_i > self.STOPPED_SPEED or mean_speed_j > self.STOPPED_SPEED

        if bbox_s < 0.1 and dist_s > 0.7 and at_least_one_moving:
            bbox_s = 0.3

        dir_ij      = np.array([vj["cx"] - vi["cx"], vj["cy"] - vi["cy"]], dtype=float)
        dir_ij_norm = np.linalg.norm(dir_ij)
        if dir_ij_norm > 0 and at_least_one_moving:
            dir_unit   = dir_ij / dir_ij_norm
            approach_i = float(np.dot(motion_i,  dir_unit))
            approach_j = float(np.dot(motion_j, -dir_unit))
            if max(approach_i, approach_j) > 0:
                dist_s = min(dist_s * 1.3, 1.0)
            if approach_i > 0 and approach_j > 0:
                dist_s = min(dist_s * 1.15, 1.0)

        accel_i = self._rolling_accel(vi["track_id"], vi["speed"])
        accel_j = self._rolling_accel(vj["track_id"], vj["speed"])
        accel_s = float(np.clip(max(accel_i, accel_j), 0.0, 1.0))

        union_box = (
            max(0, min(vi["box"][0], vj["box"][0]) - 10),
            max(0, min(vi["box"][1], vj["box"][1]) - 10),
            min(flow_mag.shape[1], max(vi["box"][2], vj["box"][2]) + 10),
            min(flow_mag.shape[0], max(vi["box"][3], vj["box"][3]) + 10),
        )
        chaos_s = OpticalFlowAnalyzer.roi_chaos(flow_mag, union_box, self.MAX_CHAOS_PX)

        if chaos_s < 0.02:
            chaos_s = 0.0
        elif chaos_s > 0:
            chaos_s = min(chaos_s * 2.5, 1.0)
        else:
            chaos_s = 0.0

        max_recent_speed = max(mean_speed_i, mean_speed_j)
        fast_crash_bonus = 0.0

        score = (
            self.W_BBOX  * bbox_s  +
            self.W_DIST  * dist_s  +
            self.W_ACCEL * accel_s +
            self.W_CHAOS * chaos_s +
            fast_crash_bonus
        )

        if centre_dist < 10:
            score = max(score, 0.95)
        if dist_s > 0.8 and accel_s > 0.3 and at_least_one_moving:
            score += 0.2
        if centre_dist < 120:
            score += 0.3
        if dist_s > 0.6 and bbox_s > 0.05:
            score += 0.25
        if centre_dist < 80 and chaos_s > 0.1:
            score = max(score, 0.7)
            
        if centre_dist < 100 and chaos_s > 0.2:
            score = max(score, 0.8)

        if centre_dist < 120:
            score = max(score, 0.75)
        if centre_dist < 80:
            score = max(score, 0.85)
        if centre_dist < 50:
            score = max(score, 0.95)

        return score, {
            "bbox":  round(bbox_s,  3),
            "dist":  round(dist_s,  3),
            "accel": round(accel_s, 3),
            "chaos": round(chaos_s, 3),
        }

    def _rolling_accel(self, track_id: int, current_speed: float) -> float:
        prev    = self._prev_speeds.get(track_id, current_speed)
        instant = abs(current_speed - prev)
        self._prev_speeds[track_id] = current_speed

        hist = self._speed_histories.get(track_id)
        if not hist or len(hist) < 2:
            return min(instant / max(self.MAX_ACCEL_SPEED, 0.01), 1.0)

        window        = list(hist)[-self.MOVING_WINDOW:]
        peak          = max(window)
        roll_dec      = max(0.0, peak - current_speed)
        raw           = max(instant, roll_dec)
        vehicle_scale = max(peak, self.MAX_ACCEL_SPEED)
        return float(min(raw / vehicle_scale, 1.0))

    def _extract_vehicles(self, boxes) -> list[dict]:
        vehicles = []
        if boxes is None:
            return vehicles

        for box in boxes:
            cls_id = int(box.cls[0])
            if cls_id not in _VEHICLE_CLASSES:
                continue

            track_id = int(box.id[0]) if box.id is not None else -1
            if track_id == -1:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cx, cy          = (x1 + x2) // 2, (y1 + y2) // 2
            conf            = float(box.conf[0])

            prev = self._prev_centres.get(track_id)
            if prev:
                b_size = _box_size((x1, y1, x2, y2))
                speed  = float(np.hypot(cx - prev[0], cy - prev[1]) / b_size) if b_size > 0 else 0.0
            else:
                speed = 0.0

            self._prev_centres[track_id] = (cx, cy)
            hist = self._speed_histories.setdefault(track_id, deque(maxlen=self.SPEED_HISTORY))
            hist.append(speed)

            vehicles.append({
                "track_id": track_id,
                "label":    _VEHICLE_CLASSES[cls_id],
                "conf":     conf,
                "box":      (x1, y1, x2, y2),
                "cx":       cx,
                "cy":       cy,
                "speed":    speed,
            })

        return vehicles

    def _dedup_vehicles(self, vehicles: list[dict]) -> list[dict]:
        if len(vehicles) <= 1:
            return vehicles

        keep = [True] * len(vehicles)
        for i in range(len(vehicles)):
            if not keep[i]:
                continue
            for j in range(i + 1, len(vehicles)):
                if not keep[j]:
                    continue
                if vehicles[i]["label"] != vehicles[j]["label"]:
                    continue
                if _iou(vehicles[i]["box"], vehicles[j]["box"]) > self.DEDUP_IOU_THRESH:
                    if vehicles[i]["conf"] >= vehicles[j]["conf"]:
                        keep[j] = False
                    else:
                        keep[i] = False
                        break

        return [v for v, k in zip(vehicles, keep) if k]

    def _both_stopped(self, vi: dict, vj: dict) -> bool:
        hi = list(self._speed_histories.get(vi["track_id"], deque()))
        hj = list(self._speed_histories.get(vj["track_id"], deque()))
        if len(hi) < 3 or len(hj) < 3:
            return False
        return (
            float(np.mean(hi)) < self.STOPPED_SPEED and
            float(np.mean(hj)) < self.STOPPED_SPEED
        )


def _iou(b1: tuple, b2: tuple) -> float:
    xi1 = max(b1[0], b2[0]); yi1 = max(b1[1], b2[1])
    xi2 = min(b1[2], b2[2]); yi2 = min(b1[3], b2[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    if inter == 0:
        return 0.0
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / (a1 + a2 - inter)


def _box_size(b: tuple) -> float:
    return float(np.hypot(b[2] - b[0], b[3] - b[1]))


def _rmean(dq: deque, window: int = 0) -> float:
    if not dq:
        return 0.0
    items = list(dq)[-window:] if window > 0 else list(dq)
    return float(np.mean(items)) if items else 0.0
