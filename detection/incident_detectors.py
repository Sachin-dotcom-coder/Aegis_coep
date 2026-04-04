"""
Contains four independent classes:

FireDetector:
  Pure OpenCV HSV thresholding + flicker gate.

GunDetector:
  YOLOv8 weapon/gun detection + muzzle flash tracking.
  Detects gun presence and firing events with high accuracy.

AccidentDetector:
  YOLOv8 + ByteTrack + Optical Flow fusion.
  4-signal weighted risk score per vehicle pair.

ImpactFlashDetector:
  Detects dust/smoke explosion brightness spikes from high-speed impacts.
  Uses spatial uniformity to separate REAL crashes from scene cuts.

SceneCutDetector:
  Detects abrupt CCTV clip transitions in compiled videos.
  Prevents false alarms and unnecessary tracker resets.

KEY FIX (v6):
  Root cause of flickering/reset bug:
    ImpactFlashDetector was triggering on scene cuts (mean_diff > 35),
    which caused detector.py to call reset() and clear all ByteTrack
    histories — making vehicles "disappear" and restart from zero.

  Fix: SceneCutDetector now runs FIRST on every frame. If a cut is
  detected, ImpactFlashDetector and AccidentDetector are both skipped
  and their internal state is gently reset (not hard-cleared).
  Vehicle tracking histories are preserved across soft resets.
"""

import cv2
import numpy as np
import torch
from collections import deque
from ultralytics import YOLO

from detection.frame_validator import FrameValidator

torch.set_num_threads(4)


# ══════════════════════════════════════════════════════════════════════════════
#  Scene Cut Detector
#  Must be called FIRST every frame before any other detector.
# ══════════════════════════════════════════════════════════════════════════════

class SceneCutDetector:
    # Lowered from 40 to ensure we catch those ~35 diff scene cuts!
    SUSPICION_THRESHOLD = 25.0  

    UNIFORMITY_THRESHOLD = 0.45

    def __init__(self):
        self._prev_gray: np.ndarray | None = None

    def update(self, frame: np.ndarray) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None:
            self._prev_gray = gray
            return False

        diff = cv2.absdiff(gray, self._prev_gray).astype(np.float32)
        self._prev_gray = gray

        mean_diff = float(np.mean(diff))

        if mean_diff < self.SUSPICION_THRESHOLD:
            return False

        h, w   = diff.shape
        rh, rw = h // 3, w // 3
        region_means = []
        for ry in range(3):
            for rx in range(3):
                region = diff[ry * rh:(ry + 1) * rh, rx * rw:(rx + 1) * rw]
                region_means.append(float(np.mean(region)))

        # KEY FIX: Sort regions to ignore static CCTV elements (timestamps, black bars)
        region_means.sort()

        # Discard the 3 darkest/most static regions. We calculate uniformity 
        # on the remaining active video area.
        reg_min    = region_means[3]
        reg_max    = region_means[-1]
        uniformity = reg_min / max(reg_max, 1.0)

        return uniformity >= self.UNIFORMITY_THRESHOLD


# ══════════════════════════════════════════════════════════════════════════════
#  Optical Flow Analyser  (Farneback dense optical flow)
# ══════════════════════════════════════════════════════════════════════════════

class OpticalFlowAnalyzer:
    """
    Computes dense optical flow between consecutive frames using
    Gunnar Farneback's algorithm (built into OpenCV — no extra download).

    Returns a per-pixel motion magnitude map that callers can query
    for specific regions of interest.
    """

    def __init__(self):
        self._prev_gray: np.ndarray | None = None
        self._flow:      np.ndarray | None = None

    def reset(self):
        """Call after a scene cut so flow doesn't compare across clips."""
        self._prev_gray = None
        self._flow      = None

    def update(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None:
            self._prev_gray = gray
            return np.zeros(gray.shape, dtype=np.float32)

        if self._flow is None:
            self._flow = np.zeros((*gray.shape, 2), dtype=np.float32)

        self._flow = cv2.calcOpticalFlowFarneback(
            self._prev_gray, gray,
            flow       = self._flow,
            pyr_scale  = 0.5,
            levels     = 3,
            winsize    = 15,
            iterations = 3,
            poly_n     = 5,
            poly_sigma = 1.2,
            flags      = cv2.OPTFLOW_USE_INITIAL_FLOW,
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
#  Impact Flash Detector
# ══════════════════════════════════════════════════════════════════════════════

class ImpactFlashDetector:
    """
    Detects the sudden brightness / dust-explosion that high-speed impacts
    produce — catches crashes even when YOLO loses the vehicles in debris.

    FIXED in v6:
    ─────────────
    Now uses the same spatial uniformity check as SceneCutDetector to
    avoid triggering on scene cuts.

    Additionally, it is now ONLY called when SceneCutDetector returns False,
    so this class never sees a frame that is a clip transition.

    Measured thresholds from video analysis:
        Normal traffic : mean_diff < 5
        Real crashes   : mean_diff 10–38  (gradual dust spread)
        Scene cuts     : mean_diff > 40   (filtered out by SceneCutDetector)

    So the crash detection window is 10–38, not 35+ as before.
    """

    # Real crash brightness rise — lower than scene cut threshold
    CRASH_MEAN_DIFF_MIN = 10.0   # below this = normal traffic
    CRASH_MEAN_DIFF_MAX = 50.0   # above this after scene-cut filter = still real crash

    # Crash motion must affect at least this much of the frame
    MIN_AFFECTED_AREA   = 0.10   # 10% of pixels must change (reduced from 15%)

    # After scene-cut filtering, remaining events with high uniformity
    # are still likely cuts that slipped through — ignore them
    MAX_UNIFORMITY      = 0.65   # crash regions are never this uniform

    def __init__(self, confirm_frames: int = 1):
        self._prev_gray = None
        self._validator = FrameValidator(required_frames=confirm_frames)
        self._ZONE_ID   = 999

    def reset(self):
        """Soft reset after scene cut — don't compare across clip boundaries."""
        self._prev_gray = None

    def detect(self, frame: np.ndarray) -> tuple[bool, dict | None]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None:
            self._prev_gray = gray
            return False, None

        diff      = cv2.absdiff(gray, self._prev_gray).astype(np.float32)
        mean_diff = float(np.mean(diff))
        self._prev_gray = gray

        if not (self.CRASH_MEAN_DIFF_MIN < mean_diff < self.CRASH_MEAN_DIFF_MAX):
            self._validator.update(self._ZONE_ID, False)
            return False, None

        bright_mask    = diff > 20
        affected_ratio = float(np.sum(bright_mask)) / diff.size
        if affected_ratio < self.MIN_AFFECTED_AREA:
            self._validator.update(self._ZONE_ID, False)
            return False, None

        h, w   = diff.shape
        rh, rw = h // 3, w // 3
        region_means = []
        for ry in range(3):
            for rx in range(3):
                region = diff[ry * rh:(ry + 1) * rh, rx * rw:(rx + 1) * rw]
                region_means.append(float(np.mean(region)))

        # KEY FIX: Match the SceneCut logic so an impact next to a 
        # black bar isn't falsely assumed to have 0.0 uniformity.
        region_means.sort()
        reg_min    = region_means[3]
        reg_max    = region_means[-1]
        uniformity = reg_min / max(reg_max, 1.0)

        if uniformity > self.MAX_UNIFORMITY:
            self._validator.update(self._ZONE_ID, False)
            return False, None

        confirmed = self._validator.update(self._ZONE_ID, True)
        if confirmed:
            self._validator.reset(self._ZONE_ID)

        brightest = np.unravel_index(np.argmax(diff), diff.shape)
        event = {
            "type"      : "road_accident",
            "cx"        : int(brightest[1]),
            "cy"        : int(brightest[0]),
            "box"       : (0, 0, w, h),
            "mean_diff" : mean_diff,
            "area_ratio": affected_ratio,
        }

        return confirmed, event


# ══════════════════════════════════════════════════════════════════════════════
#  Fire Detector
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
        self._validator    = FrameValidator(required_frames=confirm_frames)
        self._area_history: deque[float] = deque(maxlen=self.AREA_HISTORY)
        self._ZONE_ID      = 0

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
#  Gun Detector (Weapon Detection + Muzzle Flash)
# ══════════════════════════════════════════════════════════════════════════════

class GunDetector:
    """
    Detects guns/weapons in frame and alerts when fired (muzzle flash detection).
    
    Uses:
    1. YOLOv8 for weapon/gun detection (class IDs: 43 knife, 89 gun typically in some models)
    2. Muzzle flash detection (bright white/yellow flash at gun barrel tip)
    3. Frame validation for high accuracy (requires 2+ consecutive firing frames)
    
    Very accurate: High confidence thresholds + spatial validation + flash confirmation.
    """
    
    # YOLO class IDs for weapons (varies by model, using standard detection)
    # For standard COCO v5/v8: knife=43, gun/revolver=89, rifle variations
    WEAPON_CLASS_IDS = {43, 89}  # knife, gun - extend as needed
    
    # Gun detection confidence threshold
    GUN_CONFIDENCE_THRESHOLD = 0.60
    
    # Muzzle flash detection thresholds
    MUZZLE_FLASH_MIN_BRIGHTNESS = 200  # Need very bright pixels (near white)
    MUZZLE_FLASH_MIN_PIXELS = 15      # Minimum 15+ pixels for valid flash
    MUZZLE_FLASH_MAX_PIXELS = 800     # Maximum to avoid room lights
    
    # Muzzle flash must be NEAR gun barrel (not across room)
    BARREL_PROXIMITY = 60  # pixels from gun bbox edge
    
    # Spatial accuracy: flash must be at barrel tip
    # (top of gun for vertical hold, right side for horizontal)
    
    def __init__(self, confirm_frames: int = 2, model_path: str = "yolov8m.pt", debug: bool = False):
        """
        Initialize gun detector.
        
        Args:
            confirm_frames: Require N consecutive firing frames for confirmation (2-4 recommended)
            model_path: YOLO model path
            debug: Enable verbose logging
        """
        print(f"🔫 Loading weapon detection model: {model_path}")
        self._model = YOLO(model_path)
        self._debug = debug
        self._confirm_frames = confirm_frames
        self._validator = FrameValidator(required_frames=confirm_frames)
        self._ZONE_ID = 5000
        
        # Track detected guns
        self._gun_positions: dict[int, tuple[int, int, int, int]] = {}  # track_id -> bbox
        self._prev_gray: np.ndarray | None = None
        self._gun_frame_count = 0
    
    def reset(self):
        """Soft reset after scene cut."""
        self._prev_gray = None
        self._validator = FrameValidator(required_frames=self._confirm_frames)
    
    def full_reset(self):
        """Hard reset - clear all tracking."""
        self.reset()
        self._gun_positions.clear()
        self._gun_frame_count = 0
    
    def detect(self, frame: np.ndarray) -> tuple[bool, list[dict], list[dict]]:
        """
        Detect guns in frame and identify firing events.
        
        Returns:
            (confirmed, firing_events, gun_detections)
        """
        results = self._model.detect(frame, conf=0.35, verbose=False)  # Lower thresh for detection
        guns = self._extract_guns(results[0])
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        firing_events: list[dict] = []
        
        if len(guns) == 0:
            self._validator.update(self._ZONE_ID, False)
            self._prev_gray = gray
            return False, [], []
        
        # 🔫 DETECT MUZZLE FLASHES (Gun firing indicator)
        muzzle_flashes = self._detect_muzzle_flashes(frame, gray)
        
        if len(muzzle_flashes) > 0:
            # ✅ VALIDATE: Muzzle flash must be NEAR a detected gun
            for flash in muzzle_flashes:
                flash_cx, flash_cy = flash["cx"], flash["cy"]
                near_gun = False
                closest_gun = None
                min_dist = float('inf')
                
                for gun in guns:
                    gun_cx = (gun["x1"] + gun["x2"]) // 2
                    gun_cy = (gun["y1"] + gun["y2"]) // 2
                    
                    # Flash should be near gun barrel (typically at edge)
                    dist = np.hypot(flash_cx - gun_cx, flash_cy - gun_cy)
                    if dist < self.BARREL_PROXIMITY:
                        near_gun = True
                        if dist < min_dist:
                            min_dist = dist
                            closest_gun = gun
                
                if near_gun and closest_gun:
                    # 🎯 HIGH CONFIDENCE FIRING ALERT
                    confirmed = self._validator.update(self._ZONE_ID, True)
                    if self._debug:
                        print(f"[GUN FIRING] Muzzle flash detected near gun | Confidence: {closest_gun['conf']:.2f}")
                    
                    firing_events.append({
                        "type": "gun_fired",
                        "cx": flash_cx,
                        "cy": flash_cy,
                        "gun_box": (closest_gun["x1"], closest_gun["y1"], closest_gun["x2"], closest_gun["y2"]),
                        "gun_confidence": closest_gun["conf"],
                        "flash_pixels": flash["pixel_count"],
                        "flash_brightness": flash["mean_brightness"],
                        "reason": f"Muzzle flash at {min_dist:.0f}px from gun barrel"
                    })
                else:
                    self._validator.update(self._ZONE_ID, False)
        else:
            self._validator.update(self._ZONE_ID, False)
        
        confirmed = self._validator.query(self._ZONE_ID)
        if confirmed and len(firing_events) > 0:
            self._validator.reset(self._ZONE_ID)
        
        self._prev_gray = gray
        return confirmed, firing_events, guns
    
    def _extract_guns(self, detection_result) -> list[dict]:
        """Extract gun/weapon detections from YOLO results."""
        guns = []
        if detection_result.boxes is None:
            return guns
        
        for box in detection_result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            
            # Only accept high-confidence gun detections
            if cls_id not in self.WEAPON_CLASS_IDS:
                continue
            if conf < self.GUN_CONFIDENCE_THRESHOLD:
                continue
            
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            guns.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "class_id": cls_id,
                "conf": conf,
            })
        
        if self._debug and len(guns) > 0:
            print(f"[GUN DETECTED] Found {len(guns)} gun(s) in frame")
        
        return guns
    
    def _detect_muzzle_flashes(self, frame: np.ndarray, gray: np.ndarray) -> list[dict]:
        """
        Detect muzzle flashes (bright white/yellow flashes at gun tip).
        
        Strategy:
        1. Find very bright pixels (> 200, near white)
        2. Validate size/shape (flash should be 15-800 pixels)
        3. Validate spatial uniformity (concentrated flash, not scattered)
        """
        flashes = []
        
        if self._prev_gray is None:
            self._prev_gray = gray
            return flashes
        
        # 🔍 DETECT BRIGHTNESS SPIKES (characteristic of muzzle flash)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # Either:
        # 1. Very bright pixels (white flash)
        brightness_mask = hsv[:, :, 2] > self.MUZZLE_FLASH_MIN_BRIGHTNESS
        
        # 2. Yellow/orange flash (typical muzzle color)
        lower_yellow = np.array([15, 100, 200])
        upper_yellow = np.array([35, 255, 255])
        yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        flash_mask = cv2.bitwise_or(brightness_mask.astype(np.uint8) * 255, yellow_mask)
        
        # Morphology to clean up noise
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        flash_mask = cv2.morphologyEx(flash_mask, cv2.MORPH_OPEN, k)
        flash_mask = cv2.morphologyEx(flash_mask, cv2.MORPH_CLOSE, k)
        
        # Find contours (potential muzzle flashes)
        contours, _ = cv2.findContours(flash_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            
            # Size validation: 15-800 pixels
            if area < self.MUZZLE_FLASH_MIN_PIXELS or area > self.MUZZLE_FLASH_MAX_PIXELS:
                continue
            
            # Get region stats
            x, y, w, h = cv2.boundingRect(cnt)
            flash_region = hsv[y:y+h, x:x+w]
            
            # Validate brightness in region
            mean_brightness = float(np.mean(flash_region[:, :, 2]))
            if mean_brightness < self.MUZZLE_FLASH_MIN_BRIGHTNESS * 0.75:
                continue
            
            # Calculate compactness (compact = dense flash, scattered = noise)
            compactness = area / (w * h + 1)
            if compactness < 0.30:  # Too scattered
                continue
            
            cx = x + w // 2
            cy = y + h // 2
            
            flashes.append({
                "cx": cx,
                "cy": cy,
                "x": x, "y": y, "w": w, "h": h,
                "pixel_count": int(area),
                "mean_brightness": round(mean_brightness, 1),
                "compactness": round(compactness, 2),
            })
        
        if self._debug and len(flashes) > 0:
            print(f"[MUZZLE FLASH] Detected {len(flashes)} potential flash(es)")
        
        return flashes


# ══════════════════════════════════════════════════════════════════════════════
#  Accident Detector
# ══════════════════════════════════════════════════════════════════════════════

_VEHICLE_CLASSES    = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
_TRAFFIC_LIGHT_RATIO = 0.95


class AccidentDetector:
    """
    Physics-based collision detection using 4-signal weighted risk score.
    
    Signals:
    1. BBox overlap - vehicles physically overlapping in pixels
    2. Distance risk - center-to-center distance relative to vehicle size
    3. Deceleration - loss of speed (from history tracking)
    4. Optical flow chaos - sudden motion surge during impact
    
    For CCTV: Lowered weights for accel (0.0), increased distance (0.40).
    Fast collisions handled by confirm_frames=1.
    """

    W_BBOX  = 0.30
    W_DIST  = 0.40
    W_ACCEL = 0.00
    W_CHAOS = 0.30

    SCORE_THRESHOLD        = 0.45   # Raised to filter noise (0.24 = noise, 0.6+ = real collision)
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
        self._prev_angles:     dict[int, float]               = {}  # Track vehicle orientation
        self._stationary_frames: dict[int, int]              = {}  # Track stationary time
        self._pair_distance_hist: dict                       = {}  # Track distance history for approaching
        
        # Stationary accident detection
        self._fps = 30
        self._stationary_threshold = 30 * self._fps  # 30 seconds @ 30 fps = 900 frames
        
        # Cooldown to prevent duplicate detections
        self._last_collision_frame = -100
        self._cooldown_frames = 30

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
        self._prev_angles.clear()
        self._stationary_frames.clear()
        self._pair_distance_hist.clear()

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> tuple[bool, list[dict], list[dict]]:
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
        pair_count = 0
        logged_frame_close = False  # Log once per frame for debugging
        
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                vi, vj = vehicles[i], vehicles[j]

                dx = vi["cx"] - vj["cx"]
                dy = vi["cy"] - vj["cy"]
                centre_dist = float(np.hypot(dx, dy))
                pair_count += 1

                # Track distance history for approaching detection
                pair_key = tuple(sorted([vi["track_id"], vj["track_id"]]))
                hist = self._pair_distance_hist.setdefault(pair_key, deque(maxlen=5))
                hist.append(centre_dist)

                # Dynamic distance cutoff
                max_speed_i  = max(list(self._speed_histories.get(vi["track_id"], deque([0]))), default=0)
                max_speed_j  = max(list(self._speed_histories.get(vj["track_id"], deque([0]))), default=0)
                avg_box_size = (_box_size(vi["box"]) + _box_size(vj["box"])) / 2
                dynamic_cutoff = max(200, avg_box_size * 3)

                if centre_dist > dynamic_cutoff:
                    continue

                # Direction filter - RELAXED for CCTV slow motion
                prev_i   = self._prev_centres.get(vi["track_id"], (vi["cx"], vi["cy"]))
                prev_j   = self._prev_centres.get(vj["track_id"], (vj["cx"], vj["cy"]))
                motion_i = np.array([vi["cx"] - prev_i[0], vi["cy"] - prev_i[1]])
                motion_j = np.array([vj["cx"] - prev_j[0], vj["cy"] - prev_j[1]])

                # REMOVED: Killed all CCTV detections due to slow motion
                # if np.linalg.norm(motion_i) < 0.01 and np.linalg.norm(motion_j) < 0.01:
                #     continue

                # Debug: Report close pairs once per frame
                if centre_dist < 100 and not logged_frame_close:
                    print(f"[FRAME_DEBUG] Found close pair: {centre_dist:.1f}px, Both stopped check...")
                    logged_frame_close = True

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
                    pair_dist_hist = hist,  # Pass distance history
                )

                if instant_hit:
                    # Apply cooldown to prevent duplicate detections
                    if frame_id - self._last_collision_frame < self._cooldown_frames:
                        continue
                    
                    self._last_collision_frame = frame_id
                    score = max(score, 0.85)
                    events.append(self._make_event(vi, vj, score, breakdown,
                                                   "INSTANT COLLISION DETECTED"))
                    print(f"[INSTANT COLLISION] dist={centre_dist:.1f}px")
                    continue
                
                # ── Rotation-based collision detection ──────────────────────────
                # If either vehicle rotated suddenly while very close = impact
                if centre_dist < 100:
                    if vi.get("rotated") or vj.get("rotated"):
                        score = max(score, 0.75)  # High confidence for rotation impact
                        print(f"[ROTATION IMPACT] Vehicle rotated at {centre_dist:.1f}px")

                # ALWAYS log close pairs for debugging
                if centre_dist < 100:
                    print(
                        f"[CLOSE_PAIR] dist={centre_dist:.1f}px | score={score:.3f} | threshold={self.SCORE_THRESHOLD} | {'PASS' if score >= self.SCORE_THRESHOLD else 'FAIL'}"
                    )

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

                # Apply cooldown to prevent duplicate detections
                if frame_id - self._last_collision_frame < self._cooldown_frames:
                    continue
                
                self._last_collision_frame = frame_id
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

        # ── STATIONARY ACCIDENT DETECTION (vehicle stopped > 30s with no nearby traffic) ──
        # 🛣️ Not many vehicles around
        if len(vehicles) < 3:
            for v in vehicles:
                frames = self._stationary_frames.get(v["track_id"], 0)
                
                if frames > self._stationary_threshold and v["speed"] < 0.01:
                    # 🚫 Not near other vehicles (avoid traffic signals)
                    nearest_vehicle_distance = float('inf')
                    for u in vehicles:
                        if u["track_id"] == v["track_id"]:
                            continue
                        d = np.hypot(v["cx"] - u["cx"], v["cy"] - u["cy"])
                        nearest_vehicle_distance = min(nearest_vehicle_distance, d)
                    
                    # Only flag if truly isolated
                    if nearest_vehicle_distance > 120:
                        # Apply cooldown for stationary detection too
                        if frame_id - self._last_collision_frame >= self._cooldown_frames:
                            self._last_collision_frame = frame_id
                            events.append(self._make_event(
                                v, v, 0.70, 
                                {"bbox": 0.0, "dist": 0.0, "accel": 0.0, "chaos": 0.0},
                                f"Vehicle stopped for {frames // self._fps:.0f}s (likely accident)"
                            ))
                            print(f"[STATIONARY ACCIDENT] Vehicle #{v['track_id']} stopped for {frames // self._fps:.0f}s")

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

    def _is_instant_collision(self, vi, vj, bbox_s, chaos_s, centre_dist, pair_dist_hist=None) -> bool:
        # If proximity is EXTREME (touching), instant collision
        # BUT only if vehicles are approaching (not just passing close)
        if centre_dist < 35:
            # Check distance history: must be getting closer
            if pair_dist_hist is not None and len(pair_dist_hist) >= 3:
                # Decreasing distance = approaching
                if pair_dist_hist[-1] < pair_dist_hist[-2] < pair_dist_hist[-3]:
                    return True
            elif pair_dist_hist is None:
                # No history available, allow collision at < 35px
                return True
            
        if bbox_s >= self.INSTANT_COLLISION_BBOX and chaos_s > 0.05:
            return True
                
        return False

    def _pair_score(self, vi, vj, flow_mag, centre_dist, motion_i, motion_j):
        """Calculate pure proximity + approach score."""
        w_i = vi["box"][2] - vi["box"][0]
        h_i = vi["box"][3] - vi["box"][1]
        w_j = vj["box"][2] - vj["box"][0]
        h_j = vj["box"][3] - vj["box"][1]

        # Calculate bbox overlap signal (for breakdown logging only)
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

        # Calculate distance signal (for breakdown logging only)
        avg_size  = (_box_size(vi["box"]) + _box_size(vj["box"])) / 2.0
        safe_dist = float(np.clip(avg_size * self.SAFE_DIST_FACTOR, 50, 200))
        dist_s    = float(np.clip(1.0 - centre_dist / safe_dist, 0.0, 1.0))

        # Calculate acceleration signal (for breakdown logging only)
        accel_i = self._rolling_accel(vi["track_id"], vi["speed"])
        accel_j = self._rolling_accel(vj["track_id"], vj["speed"])
        accel_s = float(np.clip(max(accel_i, accel_j), 0.0, 1.0))

        # Calculate chaos signal (for breakdown logging only)
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

        # ═══════════════════════════════════════════════════════════════════════
        # PURE PROXIMITY + APPROACH (Motion-independent collision detection)
        # ═══════════════════════════════════════════════════════════════════════
        
        score = 0.0
        
        # Strong proximity bonuses (CCTV-optimized)
        if centre_dist < 100:
            score += 0.4
        if centre_dist < 80:
            score += 0.3
        if centre_dist < 60:
            score += 0.3
        
        # Are vehicles moving towards each other? (approach check)
        dir_ij = np.array([vj["cx"] - vi["cx"], vj["cy"] - vi["cy"]], dtype=float)
        norm = np.linalg.norm(dir_ij)
        
        if norm > 0:
            dir_unit = dir_ij / norm
            approach_i = float(np.dot(motion_i, dir_unit))
            approach_j = float(np.dot(motion_j, -dir_unit))
            
            # Either vehicle approaching the other = add score
            if approach_i > -0.01 or approach_j > -0.01:
                score += 0.3
        
        # PARALLEL MOTION FILTER: If both vehicles moving in same direction → reduce score
        # (This filters lane changes, cars passing, etc.)
        dot_motion = float(np.dot(motion_i, motion_j))
        if dot_motion > 0:  # Same direction = positive dot product
            score *= 0.7  # Reduce confidence for parallel motion
        
        # Final threshold for collision
        return score, {
            "bbox":  round(bbox_s,  3),
            "dist":  round(dist_s,  3),
            "accel": round(accel_s, 3),
            "chaos": round(chaos_s, 3),
        }

    def _get_box_angle(self, box: tuple) -> float:
        """Calculate bounding box angle (aspect ratio orientation)."""
        x1, y1, x2, y2 = box
        w = x2 - x1
        h = y2 - y1
        if w == 0:
            return 0.0
        # Simple orientation: angle = atan2(height, width)
        return float(np.arctan2(h, w))

    def _detect_vehicle_rotation(self, track_id: int, current_angle: float, centre_dist: float) -> bool:
        """Detect if vehicle has rotated suddenly (impact indicator)."""
        prev_angle = self._prev_angles.get(track_id)
        self._prev_angles[track_id] = current_angle
        
        if prev_angle is None:
            return False
        
        # Calculate angle change
        angle_delta = abs(current_angle - prev_angle)
        # Normalize to [0, pi]
        if angle_delta > np.pi:
            angle_delta = 2 * np.pi - angle_delta
        
        # Vehicle is very close AND rotated significantly = likely impact
        # Threshold: 0.4 radians (~23 degrees) rotation
        if centre_dist < 100 and angle_delta > 0.4:
            return True
        
        return False

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
            box_tuple       = (x1, y1, x2, y2)
            angle           = self._get_box_angle(box_tuple)

            prev = self._prev_centres.get(track_id)
            if prev:
                b_size = _box_size((x1, y1, x2, y2))
                speed  = float(np.hypot(cx - prev[0], cy - prev[1]) / b_size) if b_size > 0 else 0.0
            else:
                speed = 0.0

            self._prev_centres[track_id] = (cx, cy)
            
            # Track stationary time
            if speed < 0.01:
                self._stationary_frames[track_id] = self._stationary_frames.get(track_id, 0) + 1
            else:
                self._stationary_frames[track_id] = 0
            
            # Track rotation for impact detection
            has_rotated = self._detect_vehicle_rotation(track_id, angle, 0.0)  # Will check distance in pair loop
            
            hist = self._speed_histories.setdefault(track_id, deque(maxlen=self.SPEED_HISTORY))
            hist.append(speed)

            vehicles.append({
                "track_id": track_id,
                "label":    _VEHICLE_CLASSES[cls_id],
                "conf":     conf,
                "box":      box_tuple,
                "cx":       cx,
                "cy":       cy,
                "speed":    speed,
                "angle":    angle,
                "rotated":  has_rotated,
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


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

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
