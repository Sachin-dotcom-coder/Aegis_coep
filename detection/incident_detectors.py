"""
Contains two independent classes:

FireDetector:
  Pure OpenCV HSV thresholding + flicker gate.

AccidentDetector:
  YOLOv8s + ByteTrack + Optical Flow fusion.

  Instead of a single IoU threshold, each vehicle pair gets a combined
  risk score from four signals:

      score = 0.4 * bbox_overlap
            + 0.3 * distance_risk
            + 0.2 * acceleration_spike
            + 0.1 * motion_chaos

  bbox_overlap     — IoU of the two bounding boxes (0→1).
  distance_risk    — Proximity: 1 when touching, 0 when far apart.
  acceleration_spike — Sharp deceleration of either vehicle (0→1).
  motion_chaos     — Optical flow chaos (Farneback std-dev) in the
                     combined ROI. Catches crashes even when bbox
                     detection partially fails.

  If score > SCORE_THRESHOLD for N consecutive frames → CONFIRMED.
"""

import cv2
import numpy as np
import torch
from collections import deque
from ultralytics import YOLO

from detection.frame_validator import FrameValidator

torch.set_num_threads(4)


# ══════════════════════════════════════════════════════════════════════════════
#  Optical Flow Analyser  (Farneback dense optical flow)
# ══════════════════════════════════════════════════════════════════════════════

class OpticalFlowAnalyzer:
    """
    Computes dense optical flow between consecutive frames using
    Gunnar Farneback's algorithm (built into OpenCV — no extra download).

    Returns a per-pixel motion magnitude map that callers can query
    for specific regions of interest.

    Why Farneback?
    ─────────────
    • Works on every pixel, not just tracked points.
    • Captures chaotic motion that YOLO misses (post-crash debris, skid).
    • Fast enough for real-time on CPU at 320-416px.
    """

    def __init__(self):
        self._prev_gray: np.ndarray | None = None
        self._flow:      np.ndarray | None = None   # reused across calls (warm-start)

    def update(self, frame: np.ndarray) -> np.ndarray:
        """
        Feed the next BGR frame. Returns a float32 magnitude map (HxW).
        On the very first call returns all-zeros (no previous frame yet).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None:
            self._prev_gray = gray
            return np.zeros(gray.shape, dtype=np.float32)

        if self._flow is None:
            self._flow = np.zeros((*gray.shape, 2), dtype=np.float32)

        self._flow = cv2.calcOpticalFlowFarneback(
            self._prev_gray, gray,
            flow=self._flow,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=cv2.OPTFLOW_USE_INITIAL_FLOW,
        )
        self._prev_gray = gray

        mag = np.sqrt(
            self._flow[..., 0] ** 2 +
            self._flow[..., 1] ** 2
        ).astype(np.float32)
        return mag

    @staticmethod
    def roi_chaos(mag: np.ndarray, box: tuple[int, int, int, int],
                  max_chaos_px: float = 25.0) -> float:
        """
        Return motion chaos score [0, 1] for a bounding-box ROI.
        chaos = std-dev of flow magnitudes inside the box, normalised.
        A uniform flow (car moving smoothly) has low std-dev.
        A crash produces chaotic, multi-directional pixels → high std-dev.
        """
        h, w = mag.shape
        x1, y1, x2, y2 = (
            max(0, box[0]), max(0, box[1]),
            min(w, box[2]), min(h, box[3]),
        )
        if x2 <= x1 or y2 <= y1:
            return 0.0
        roi = mag[y1:y2, x1:x2]
        return float(min(np.std(roi) / max_chaos_px, 1.0))


# ══════════════════════════════════════════════════════════════════════════════
#  Fire Detector  (unchanged from v3)
# ══════════════════════════════════════════════════════════════════════════════

class FireDetector:
    """
    Detects visible fire from a BGR frame using HSV colour thresholding.
    Requires flickering (variable area) + minimum brightness + minimum size.
    """

    _LOWER_A = np.array([5,   140, 170])
    _UPPER_A = np.array([25,  255, 255])
    _LOWER_B = np.array([165, 140, 170])
    _UPPER_B = np.array([180, 255, 255])

    MIN_FIRE_AREA   = 5_000
    MIN_BRIGHTNESS  = 170
    MIN_FLICKER_STD = 300
    AREA_HISTORY    = 12

    def __init__(self, confirm_frames: int = 8):
        self._validator   = FrameValidator(required_frames=confirm_frames)
        self._area_history: deque[float] = deque(maxlen=self.AREA_HISTORY)
        self._ZONE_ID     = 0

    def detect(self, frame: np.ndarray) -> tuple[bool, list[dict]]:
        hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.bitwise_or(
            cv2.inRange(hsv, self._LOWER_A, self._UPPER_A),
            cv2.inRange(hsv, self._LOWER_B, self._UPPER_B),
        )
        k    = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        events: list[dict] = []
        total_area = 0.0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.MIN_FIRE_AREA:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            if hsv[y:y+h, x:x+w, 2].mean() < self.MIN_BRIGHTNESS:
                continue
            total_area += area
            events.append({
                "type": "fire",
                "cx":   x + w // 2,
                "cy":   y + h // 2,
                "box":  (x, y, x + w, y + h),
                "area": area,
            })

        self._area_history.append(total_area)
        enough  = len(self._area_history) == self.AREA_HISTORY
        flicker = enough and float(np.std(self._area_history)) > self.MIN_FLICKER_STD

        flagged   = len(events) > 0 and (flicker or not enough)
        confirmed = self._validator.update(self._ZONE_ID, flagged)
        if confirmed:
            self._validator.reset(self._ZONE_ID)
        return confirmed, events


# ══════════════════════════════════════════════════════════════════════════════
#  Accident Detector  (v5 — optical flow + 4-signal score fusion)
# ══════════════════════════════════════════════════════════════════════════════

_VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
_TRAFFIC_LIGHT_RATIO = 0.95   # ≥95% of vehicles stopped → treat as red light


class AccidentDetector:
    """
    Detects road accidents using a 4-signal weighted risk score per vehicle pair.

    Signals (all normalised to [0, 1]):
    ───────────────────────────────────
    bbox_overlap     (weight 0.4)
        IoU of the two bounding boxes.
        Detects when cars physically occupy the same pixels.

    distance_risk    (weight 0.3)
        Proximity score: 1.0 when boxes are touching,
        decays to 0.0 at SAFE_DIST_FACTOR × vehicle size.
        Also increases when vehicles are heading toward each other.

    acceleration_spike (weight 0.2)
        Normalised |Δspeed| — sudden braking/impact.
        Computed from the per-vehicle speed history deque.

    motion_chaos     (weight 0.1)
        Farneback dense optical flow std-dev inside the combined ROI.
        Captures crash motion even when YOLO bbox detection partially fails.

    score = 0.4·bbox_overlap + 0.3·distance_risk
          + 0.2·acceleration_spike + 0.1·motion_chaos

    If score > SCORE_THRESHOLD for N consecutive frames → CONFIRMED.
    """

    # ── Scoring weights (must sum to 1.0) ─────────────────────────────────────
    W_BBOX  = 0.45 #Detects physical overlap
    W_DIST  = 0.20 #Detects proximity and direction 1 - (distance / safe_distance)
    W_ACCEL = 0.05 #Detects sudden braking or impact
    W_CHAOS = 0.30 #Detects chaotic motion

    SCORE_THRESHOLD   = 0.40   # lower threshold so CCTV slow-motion triggers
    SAFE_DIST_FACTOR  = 2.2    # wider safe zone; dist_s decays more gradually
    MAX_ACCEL_SPEED   = 0.3    # normalized accel ceiling
    MAX_CHAOS_PX      = 8.0    # tighter flow threshold reduces noise floor
    DEDUP_IOU_THRESH  = 0.85   # collapse nearly-identical YOLO boxes (same detection)
    STOPPED_SPEED     = 0.05   # normalized speed — below this = vehicle stopped
    MOVING_WINDOW     = 8      # frames of history used in rolling calculations
    SPEED_HISTORY     = 25

    def __init__(
        self,
        confirm_frames: int = 2,
        model_path: str = "yolov8m.pt",
        debug: bool = False,
    ):
        print(f"🔄 Loading vehicle detection model: {model_path}")
        self._model     = YOLO(model_path)
        self._validator = FrameValidator(required_frames=confirm_frames)
        self._flow_analyzer = OpticalFlowAnalyzer()
        self._debug     = debug
        self._ZONE_ID   = 0

        # Keyed by ByteTrack ID
        self._prev_centres:    dict[int, tuple[float, float]] = {}
        self._speed_histories: dict[int, deque]               = {}
        self._prev_speeds:     dict[int, float]               = {}

    # ── Public ────────────────────────────────────────────────────────────────

    def detect(
        self, frame: np.ndarray
    ) -> tuple[bool, list[dict], list[dict]]:
        """
        Returns:
            confirmed : bool
            events    : list[dict]  — accident events with score breakdown
            vehicles  : list[dict]  — all tracked vehicles (for drawing)
        """
        # ── 1. YOLO track ─────────────────────────────────────────────────────
        results  = self._model.track(
            frame, imgsz=416, persist=True, verbose=False
        )
        vehicles = self._extract_vehicles(results[0].boxes)
        vehicles = self._dedup_vehicles(vehicles)

        # ── 2. Optical flow magnitude map for this frame ───────────────────────
        flow_mag = self._flow_analyzer.update(frame)

        events: list[dict] = []

        # ── 3. Traffic-light guard ─────────────────────────────────────────────
        if len(vehicles) >= 3:
            n_stopped = sum(
                1 for v in vehicles
                if _rmean(self._speed_histories.get(v["track_id"], deque()),
                          self.MOVING_WINDOW) < self.STOPPED_SPEED
            )
            if n_stopped / len(vehicles) >= _TRAFFIC_LIGHT_RATIO:
                self._validator.update(self._ZONE_ID, False)
                return False, [], vehicles

        # ── 4. Per-pair risk scoring ───────────────────────────────────────────
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                vi, vj = vehicles[i], vehicles[j]

                # Issue 5: O(n^2) scaling — only compare nearby vehicles
                dx = vi["cx"] - vj["cx"]
                dy = vi["cy"] - vj["cy"]
                centre_dist = float(np.hypot(dx, dy))
                if centre_dist > 200:
                    continue

                # Issue 6: Direction filter — ignore fully stationary combinations instead of same-direction
                prev_i = self._prev_centres.get(vi["track_id"], (vi["cx"], vi["cy"]))
                prev_j = self._prev_centres.get(vj["track_id"], (vj["cx"], vj["cy"]))
                motion_i = np.array([vi["cx"] - prev_i[0], vi["cy"] - prev_i[1]])
                motion_j = np.array([vj["cx"] - prev_j[0], vj["cy"] - prev_j[1]])
                if np.linalg.norm(motion_i) < 0.01 and np.linalg.norm(motion_j) < 0.01:
                    continue

                # Skip pairs where both vehicles have been continuously stopped —
                # covers parked cars and 2-car red-light stops.
                if self._both_stopped(vi, vj):
                    continue

                score, breakdown = self._pair_score(vi, vj, flow_mag, centre_dist, motion_i, motion_j)

                if self._debug:
                    print(
                        f"[Accident] #{vi['track_id']} {vi['label']} vs "
                        f"#{vj['track_id']} {vj['label']} → "
                        f"score={score:.3f}  "
                        f"(bbox={breakdown['bbox']:.2f} "
                        f"dist={breakdown['dist']:.2f} "
                        f"accel={breakdown['accel']:.2f} "
                        f"chaos={breakdown['chaos']:.2f})"
                    )

                if score < self.SCORE_THRESHOLD:
                    continue

                events.append({
                    "type":    "road_accident",
                    "cx":      (vi["cx"] + vj["cx"]) // 2,
                    "cy":      (vi["cy"] + vj["cy"]) // 2,
                    "box": (
                        min(vi["box"][0], vj["box"][0]),
                        min(vi["box"][1], vj["box"][1]),
                        max(vi["box"][2], vj["box"][2]),
                        max(vi["box"][3], vj["box"][3]),
                    ),
                    "vehicles":  [vi["label"], vj["label"]],
                    "score":     round(score, 3),
                    "breakdown": breakdown,
                    "reason": (
                        f"score={score:.2f} "
                        f"(bbox={breakdown['bbox']:.2f} "
                        f"dist={breakdown['dist']:.2f} "
                        f"acc={breakdown['accel']:.2f} "
                        f"chaos={breakdown['chaos']:.2f})"
                    ),
                })

        flagged   = len(events) > 0
        confirmed = self._validator.update(self._ZONE_ID, flagged)
        if confirmed:
            self._validator.reset(self._ZONE_ID)

        return confirmed, events, vehicles

    # ── Signal computation ─────────────────────────────────────────────────────

    def _pair_score(
        self,
        vi: dict,
        vj: dict,
        flow_mag: np.ndarray,
        centre_dist: float,
        motion_i: np.ndarray,
        motion_j: np.ndarray,
    ) -> tuple[float, dict]:
        """Compute the 4-signal weighted score for a vehicle pair."""

        # ── Signal 1: AABB Optimization (replaces pure IOU) ────────────────────
        w_i = vi["box"][2] - vi["box"][0]
        h_i = vi["box"][3] - vi["box"][1]
        w_j = vj["box"][2] - vj["box"][0]
        h_j = vj["box"][3] - vj["box"][1]

        w_sum_half = (w_i + w_j) / 2.0
        h_sum_half = (h_i + h_j) / 2.0

        dx_abs = abs(vi["cx"] - vj["cx"])
        dy_abs = abs(vi["cy"] - vj["cy"])

        overlap_x = w_sum_half - dx_abs
        overlap_y = h_sum_half - dy_abs

        # Check for 5% margin to catch merged/near-miss collisions in CCTV
        margin_x = w_sum_half * 0.05
        margin_y = h_sum_half * 0.05

        if overlap_x > -margin_x and overlap_y > -margin_y:
            overlap_pct_x = min(1.0, max(0.0, overlap_x / w_sum_half)) if w_sum_half > 0 else 0
            overlap_pct_y = min(1.0, max(0.0, overlap_y / h_sum_half)) if h_sum_half > 0 else 0
            bbox_s = (overlap_pct_x + overlap_pct_y) / 2.0
            if bbox_s == 0:
                bbox_s = 0.15 
        else:
            bbox_s = 0.0

        # ── Signal 2: distance_risk ────────────────────────────────────────────
        # Safe distance scales with average vehicle size
        avg_size = (
            _box_size(vi["box"]) + _box_size(vj["box"])
        ) / 2.0
        safe_dist = float(np.clip(avg_size * self.SAFE_DIST_FACTOR, 50, 200))
        dist_raw = 1.0 - centre_dist / safe_dist
        dist_s = float(np.clip(dist_raw, 0.0, 1.0))

        # CCTV BOOST (critical) — Makes far-but-close vehicles count as risky
        if centre_dist < 150:
            dist_s = min(dist_s * 1.5, 1.0)

        # Rolling speed means used for motion-aware guards
        mean_speed_i = _rmean(
            self._speed_histories.get(vi["track_id"], deque()), self.MOVING_WINDOW
        )
        mean_speed_j = _rmean(
            self._speed_histories.get(vj["track_id"], deque()), self.MOVING_WINDOW
        )
        at_least_one_moving = (
            mean_speed_i > self.STOPPED_SPEED or mean_speed_j > self.STOPPED_SPEED
        )

        # Boost bbox_s only when at least one vehicle was recently moving —
        # prevents parked-car proximity from inflating the bbox signal.
        if bbox_s < 0.1 and dist_s > 0.7 and at_least_one_moving:
            bbox_s = 0.3

        # ── Bidirectional approaching boost ────────────────────────────────────
        # motion_i and motion_j are pre-computed and passed in.
        dir_ij = np.array([vj["cx"] - vi["cx"], vj["cy"] - vi["cy"]], dtype=float)
        dir_ij_norm = np.linalg.norm(dir_ij)
        if dir_ij_norm > 0 and at_least_one_moving:
            dir_unit   = dir_ij / dir_ij_norm
            approach_i = float(np.dot(motion_i,  dir_unit))   # vi closing on vj
            approach_j = float(np.dot(motion_j, -dir_unit))   # vj closing on vi
            if max(approach_i, approach_j) > 0:
                dist_s = min(dist_s * 1.3, 1.0)   # 30% boost if either is closing
            if approach_i > 0 and approach_j > 0:
                dist_s = min(dist_s * 1.15, 1.0)  # extra 15% boost for head-on

        # ── Signal 3: rolling deceleration ────────────────────────────────────
        # _rolling_accel returns the larger of (instant jerk, rolling peak→current)
        # so multi-frame braking and sudden impacts are both captured.
        accel_i = self._rolling_accel(vi["track_id"], vi["speed"])
        accel_j = self._rolling_accel(vj["track_id"], vj["speed"])
        accel_s = float(np.clip(
            max(accel_i, accel_j) / self.MAX_ACCEL_SPEED, 0.0, 1.0
        ))

        # ── Signal 4: motion_chaos (optical flow) ─────────────────────────────
        # ROI = union of both bounding boxes, slightly expanded
        union_box = (
            max(0, min(vi["box"][0], vj["box"][0]) - 10),
            max(0, min(vi["box"][1], vj["box"][1]) - 10),
            min(flow_mag.shape[1], max(vi["box"][2], vj["box"][2]) + 10),
            min(flow_mag.shape[0], max(vi["box"][3], vj["box"][3]) + 10),
        )
        chaos_s = OpticalFlowAnalyzer.roi_chaos(
            flow_mag, union_box, self.MAX_CHAOS_PX
        )
        if chaos_s < 0.05:
            chaos_s = 0.0
        else:
            chaos_s *= 1.3

        # ── Weighted sum ───────────────────────────────────────────────────────
        score = (
            self.W_BBOX  * bbox_s +
            self.W_DIST  * dist_s +
            self.W_ACCEL * accel_s +
            self.W_CHAOS * chaos_s
        )

        # ── Bonuses & Triggers ──────────────────────────────────────────────────
        # NEAR-COLLISION trigger requires recent motion
        if dist_s > 0.8 and accel_s > 0.3 and at_least_one_moving:
            score += 0.2

        if centre_dist < 120:
            score += 0.3

        if dist_s > 0.6 and bbox_s > 0.05:
            score += 0.25

        # HARD collision trigger (for CCTV)
        if centre_dist < 80 and chaos_s > 0.1:
            score = max(score, 0.7)

        return score, {
            "bbox":  round(bbox_s,  3),
            "dist":  round(dist_s,  3),
            "accel": round(accel_s, 3),
            "chaos": round(chaos_s, 3),
        }

    def _rolling_accel(self, track_id: int, current_speed: float) -> float:
        """
        Rolling deceleration signal — returns the LARGER of:
          • instant jerk  : |speed_now - speed_prev_frame|  (sudden impact)
          • rolling decel : peak_speed_in_window - current  (gradual braking)

        Using the history deque (already populated by _extract_vehicles)
        so we do NOT add current_speed again here.
        """
        # Instant jerk (single-frame delta)
        prev    = self._prev_speeds.get(track_id, current_speed)
        instant = abs(current_speed - prev)
        self._prev_speeds[track_id] = current_speed

        hist = self._speed_histories.get(track_id)
        if not hist or len(hist) < 2:
            return instant

        # Rolling deceleration: max speed seen recently vs current speed
        window   = list(hist)[-self.MOVING_WINDOW:]
        peak     = max(window)
        roll_dec = max(0.0, peak - current_speed)

        return max(instant, roll_dec)

    # ── Vehicle extraction + dedup ─────────────────────────────────────────────

    def _extract_vehicles(self, boxes) -> list[dict]:
        vehicles = []
        if boxes is None:
            return vehicles

        for box in boxes:
            cls_id = int(box.cls[0])
            if cls_id not in _VEHICLE_CLASSES:
                continue

            track_id        = int(box.id[0]) if box.id is not None else -1
            if track_id == -1:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cx, cy          = (x1 + x2) // 2, (y1 + y2) // 2
            conf            = float(box.conf[0])

            prev  = self._prev_centres.get(track_id)
            if prev:
                dx = cx - prev[0]
                dy = cy - prev[1]
                b_size = _box_size((x1, y1, x2, y2))
                speed = float(np.hypot(dx, dy) / b_size) if b_size > 0 else 0.0
            else:
                speed = 0.0

            self._prev_centres[track_id] = (cx, cy)

            hist = self._speed_histories.setdefault(
                track_id, deque(maxlen=self.SPEED_HISTORY)
            )
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
        """
        Collapse near-identical YOLO detections of the same car.
        Only removes pairs with IoU > DEDUP_IOU_THRESH (0.85) and same class.
        Must be well above SCORE_THRESHOLD so colliding cars are NOT removed.
        """
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
        """
        Returns True when BOTH vehicles show no meaningful movement across
        their *entire* recorded speed history.

        Using the full history — not just the recent window — means a vehicle
        that was moving before a crash still has high earlier speeds in its
        deque, so its mean stays above STOPPED_PX and the pair is NOT suppressed.

        Correctly suppresses:
          • Two parked cars side-by-side.
          • Two cars stationary at a red light (2-car case; ≥3 is caught by
            the traffic-light guard already).

        Does NOT suppress:
          • Two cars that just collided (one or both had high speed earlier).
        """
        hi = list(self._speed_histories.get(vi["track_id"], deque()))
        hj = list(self._speed_histories.get(vj["track_id"], deque()))

        # Too few data points — do not suppress; benefit of the doubt
        if len(hi) < 3 or len(hj) < 3:
            return False

        return (
            float(np.mean(hi)) < self.STOPPED_SPEED and
            float(np.mean(hj)) < self.STOPPED_SPEED
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _iou(b1: tuple, b2: tuple) -> float:
    xi1 = max(b1[0], b2[0]);  yi1 = max(b1[1], b2[1])
    xi2 = min(b1[2], b2[2]);  yi2 = min(b1[3], b2[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    if inter == 0:
        return 0.0
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / (a1 + a2 - inter)


def _box_size(b: tuple) -> float:
    """Diagonal of a bounding box — used as a scale reference."""
    return float(np.hypot(b[2] - b[0], b[3] - b[1]))


def _rmean(dq: deque, window: int = 0) -> float:
    if not dq:
        return 0.0
    items = list(dq)[-window:] if window > 0 else list(dq)
    return float(np.mean(items)) if items else 0.0
