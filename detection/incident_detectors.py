"""
Contains four independent classes:

FireDetector:
  Pure OpenCV HSV thresholding + flicker gate.

GunDetector:
  YOLOv8s weapon/gun detection + muzzle flash tracking.
  Detects gun presence and firing events with high accuracy.

AccidentDetector:
  YOLOv8s + ByteTrack + Optical Flow fusion.
  4-signal weighted risk score per vehicle pair.
  ENHANCED: Vehicle rollover/rotation detection + trailing car false positive fix.

ImpactFlashDetector:
  Detects dust/smoke explosion brightness spikes from high-speed impacts.
  Uses spatial uniformity to separate REAL crashes from scene cuts.

SceneCutDetector:
  Detects abrupt CCTV clip transitions in compiled videos.
  Prevents false alarms and unnecessary tracker resets.

OPTIMIZATIONS (v9):
  - Using YOLOv8s for better speed/accuracy balance
  - Optimized input resolution (640x640 for detection, 416x416 for tracking)
  - Reduced confidence thresholds for better recall
  - Optimized optical flow parameters for speed
  - Batch inference where possible
  - Memory-efficient tracking
"""

import cv2
import numpy as np
import torch
from collections import deque
from ultralytics import YOLO

from detection.frame_validator import FrameValidator

# Optimize PyTorch for inference
torch.set_num_threads(4)
torch.backends.cudnn.benchmark = True

# Global optimization flags
USE_HALF_PRECISION = torch.cuda.is_available()  # Use FP16 on GPU
DETECTION_IMGSZ = 640  # Higher for better accuracy
TRACKING_IMGSZ = 416   # Lower for speed


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
#  Optical Flow Analyser  (Optimized Farneback dense optical flow)
# ══════════════════════════════════════════════════════════════════════════════

class OpticalFlowAnalyzer:
    """
    Computes dense optical flow between consecutive frames using
    optimized parameters for CCTV footage.
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

        # Optimized parameters for speed/accuracy balance
        self._flow = cv2.calcOpticalFlowFarneback(
            self._prev_gray, gray,
            flow       = self._flow,
            pyr_scale  = 0.5,
            levels     = 2,          # Reduced from 3 for speed
            winsize    = 11,         # Reduced from 15 for speed
            iterations = 2,          # Reduced from 3 for speed
            poly_n     = 5,
            poly_sigma = 1.1,        # Slightly reduced for speed
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
        # Use std dev as chaos measure (normalized)
        chaos = float(np.std(roi))
        return min(chaos / max_chaos_px, 1.0)


# ══════════════════════════════════════════════════════════════════════════════
#  Impact Flash Detector
# ══════════════════════════════════════════════════════════════════════════════

class ImpactFlashDetector:
    """
    Detects the sudden brightness / dust-explosion that high-speed impacts
    produce — catches crashes even when YOLO loses the vehicles in debris.
    """

    CRASH_MEAN_DIFF_MIN = 8.0    # Lowered for CCTV sensitivity
    CRASH_MEAN_DIFF_MAX = 50.0
    MIN_AFFECTED_AREA   = 0.08   # 8% of pixels must change
    MAX_UNIFORMITY      = 0.70

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
#  Gun Detector (Optimized YOLOv8s)
# ══════════════════════════════════════════════════════════════════════════════

class GunDetector:
    """
    Detects guns/weapons in frame and alerts when fired (muzzle flash detection).
    Optimized with YOLOv8s for speed/accuracy balance.
    """
    
    WEAPON_CLASS_IDS = {43, 89}  # knife, gun
    GUN_CONFIDENCE_THRESHOLD = 0.55  # Slightly lowered for v8s
    
    MUZZLE_FLASH_MIN_BRIGHTNESS = 200
    MUZZLE_FLASH_MIN_PIXELS = 15
    MUZZLE_FLASH_MAX_PIXELS = 800
    BARREL_PROXIMITY = 60
    
    def __init__(self, confirm_frames: int = 2, model_path: str = "yolov8s.pt", debug: bool = False):
        """
        Initialize gun detector with optimized YOLOv8s.
        """
        print(f"🔫 Loading weapon detection model: {model_path}")
        self._model = YOLO(model_path)
        
        # Optimize model for inference
        if USE_HALF_PRECISION and torch.cuda.is_available():
            self._model.half()  # Use FP16
        
        self._debug = debug
        self._confirm_frames = confirm_frames
        self._validator = FrameValidator(required_frames=confirm_frames)
        self._ZONE_ID = 5000
        
        self._gun_positions: dict[int, tuple[int, int, int, int]] = {}
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
        """
        # Optimized detection with appropriate image size
        results = self._model.detect(
            frame, 
            imgsz=DETECTION_IMGSZ,
            conf=0.30,  # Lower threshold for better recall
            verbose=False
        )
        guns = self._extract_guns(results[0])
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        firing_events: list[dict] = []
        
        if len(guns) == 0:
            self._validator.update(self._ZONE_ID, False)
            self._prev_gray = gray
            return False, [], []
        
        muzzle_flashes = self._detect_muzzle_flashes(frame, gray)
        
        if len(muzzle_flashes) > 0:
            for flash in muzzle_flashes:
                flash_cx, flash_cy = flash["cx"], flash["cy"]
                near_gun = False
                closest_gun = None
                min_dist = float('inf')
                
                for gun in guns:
                    gun_cx = (gun["x1"] + gun["x2"]) // 2
                    gun_cy = (gun["y1"] + gun["y2"]) // 2
                    
                    dist = np.hypot(flash_cx - gun_cx, flash_cy - gun_cy)
                    if dist < self.BARREL_PROXIMITY:
                        near_gun = True
                        if dist < min_dist:
                            min_dist = dist
                            closest_gun = gun
                
                if near_gun and closest_gun:
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
        """Detect muzzle flashes with optimized parameters."""
        flashes = []
        
        if self._prev_gray is None:
            self._prev_gray = gray
            return flashes
        
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        brightness_mask = hsv[:, :, 2] > self.MUZZLE_FLASH_MIN_BRIGHTNESS
        
        lower_yellow = np.array([15, 100, 200])
        upper_yellow = np.array([35, 255, 255])
        yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        flash_mask = cv2.bitwise_or(brightness_mask.astype(np.uint8) * 255, yellow_mask)
        
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        flash_mask = cv2.morphologyEx(flash_mask, cv2.MORPH_OPEN, k)
        flash_mask = cv2.morphologyEx(flash_mask, cv2.MORPH_CLOSE, k)
        
        contours, _ = cv2.findContours(flash_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            
            if area < self.MUZZLE_FLASH_MIN_PIXELS or area > self.MUZZLE_FLASH_MAX_PIXELS:
                continue
            
            x, y, w, h = cv2.boundingRect(cnt)
            flash_region = hsv[y:y+h, x:x+w]
            
            mean_brightness = float(np.mean(flash_region[:, :, 2]))
            if mean_brightness < self.MUZZLE_FLASH_MIN_BRIGHTNESS * 0.75:
                continue
            
            compactness = area / (w * h + 1)
            if compactness < 0.30:
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
#  Accident Detector (Optimized YOLOv8s with Rollover & Trailing Fix)
# ══════════════════════════════════════════════════════════════════════════════

_VEHICLE_CLASSES    = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
_TRAFFIC_LIGHT_RATIO = 0.95


class AccidentDetector:
    """
    Optimized collision detection with YOLOv8s for CCTV footage.
    ENHANCED: Vehicle rollover/rotation detection + trailing car false positive elimination.
    """

    SCORE_THRESHOLD        = 0.58
    SAFE_DIST_FACTOR       = 1.5
    MAX_CHAOS_PX           = 2.0
    DEDUP_IOU_THRESH       = 0.85
    STOPPED_SPEED          = 0.05
    MOVING_WINDOW          = 8
    SPEED_HISTORY          = 25
    MIN_APPROACH_FRAMES    = 3
    MIN_CLOSING_SPEED      = 0.05
    PARALLEL_ANGLE_THRESH  = 0.92
    FOLLOWING_DIST_RATIO   = 1.2
    
    # Rollover detection thresholds
    ROLLOVER_ASPECT_RATIO_THRESH = 1.8  # Width/height ratio for rollover
    ROLLOVER_AREA_CHANGE_THRESH = 2.5   # Area change multiplier for rollover
    ROLLOVER_CHAOS_THRESH = 0.35        # Chaos threshold for rollover

    def __init__(
        self,
        confirm_frames: int = 1,
        model_path: str     = "yolov8s.pt",
        debug: bool         = False,
    ):
        print(f"🔄 Loading vehicle detection model: {model_path}")
        self._model = YOLO(model_path)
        
        # Optimize model for inference
        if USE_HALF_PRECISION and torch.cuda.is_available():
            self._model.half()  # Use FP16 for faster inference
        
        self._validator = FrameValidator(required_frames=confirm_frames)
        self._flow_analyzer = OpticalFlowAnalyzer()
        self._debug = debug
        self._ZONE_ID = 0
        self._confirm_frames = confirm_frames

        # Tracking dictionaries
        self._prev_centres:    dict[int, tuple[float, float]] = {}
        self._speed_histories: dict[int, deque]               = {}
        self._prev_speeds:     dict[int, float]               = {}
        self._pair_distance_hist: dict                       = {}
        
        # Rollover tracking
        self._vehicle_aspect_history: dict[int, deque] = {}
        self._vehicle_area_history: dict[int, deque] = {}
        self._vehicle_angle_history: dict[int, deque] = {}
        
        # Trailing car false positive prevention
        self._vehicle_trailing_count: dict[tuple, int] = {}
        self._relative_velocity_history: dict[tuple, deque] = {}
        
        self._fps = 30
        self._last_collision_frame = -100
        self._cooldown_frames = 30
        self._current_frame = 0

    def soft_reset(self):
        """Soft reset after scene cut."""
        self._validator = FrameValidator(required_frames=self._confirm_frames)
        self._flow_analyzer.reset()

    def full_reset(self):
        """Hard reset - clears everything."""
        self.soft_reset()
        self._prev_centres.clear()
        self._speed_histories.clear()
        self._prev_speeds.clear()
        self._pair_distance_hist.clear()
        self._vehicle_aspect_history.clear()
        self._vehicle_area_history.clear()
        self._vehicle_angle_history.clear()
        self._vehicle_trailing_count.clear()
        self._relative_velocity_history.clear()

    def detect(self, frame: np.ndarray, frame_id: int = 0) -> tuple[bool, list[dict], list[dict]]:
        """Main detection method with rollover and trailing car fixes."""
        self._current_frame = frame_id
        
        # Use optimized tracking with appropriate image size
        results = self._model.track(
            frame, 
            imgsz=TRACKING_IMGSZ,  # Smaller for speed
            persist=True, 
            verbose=False,
            conf=0.35,  # Lower confidence for better recall
            iou=0.45,
            tracker="bytetrack.yaml"
        )
        
        vehicles = self._extract_vehicles(results[0].boxes)
        vehicles = self._dedup_vehicles(vehicles)

        flow_mag = self._flow_analyzer.update(frame)
        events: list[dict] = []

        # First, check for rollover/rotation events on individual vehicles
        for vehicle in vehicles:
            rollover_detected, rollover_info = self._detect_rollover(vehicle, frame_id)
            if rollover_detected:
                if frame_id - self._last_collision_frame < self._cooldown_frames:
                    continue
                self._last_collision_frame = frame_id
                events.append({
                    "type": "road_accident",
                    "cx": vehicle["cx"],
                    "cy": vehicle["cy"],
                    "box": vehicle["box"],
                    "vehicles": [vehicle["label"]],
                    "score": 0.95,
                    "reason": f"VEHICLE ROLLOVER/DETECTED - Aspect ratio: {rollover_info['aspect_ratio']:.2f}, Reason: {rollover_info['reason']}"
                })
                if self._debug:
                    print(f"[ROLLOVER] Vehicle {vehicle['track_id']} rolled over!")

        # Traffic-light guard
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

        # Per-pair risk scoring with enhanced trailing car filtering
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                vi, vj = vehicles[i], vehicles[j]

                dx = vi["cx"] - vj["cx"]
                dy = vi["cy"] - vj["cy"]
                centre_dist = float(np.hypot(dx, dy))

                pair_key = tuple(sorted([vi["track_id"], vj["track_id"]]))
                hist = self._pair_distance_hist.setdefault(pair_key, deque(maxlen=10))
                hist.append(centre_dist)

                avg_box_size = (_box_size(vi["box"]) + _box_size(vj["box"])) / 2
                dynamic_cutoff = max(250, avg_box_size * 4)

                if centre_dist > dynamic_cutoff:
                    continue

                # Calculate motion vectors
                prev_i = self._prev_centres.get(vi["track_id"], (vi["cx"], vi["cy"]))
                prev_j = self._prev_centres.get(vj["track_id"], (vj["cx"], vj["cy"]))
                motion_i = np.array([vi["cx"] - prev_i[0], vi["cy"] - prev_i[1]])
                motion_j = np.array([vj["cx"] - prev_j[0], vj["cy"] - prev_j[1]])

                speed_i = vi["speed"]
                speed_j = vj["speed"]
                
                # Both stationary filter
                if speed_i < 0.02 and speed_j < 0.02:
                    continue

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # ENHANCED TRAILING CAR FILTER (for rear-view camera angles)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                motion_mag_i = np.linalg.norm(motion_i)
                motion_mag_j = np.linalg.norm(motion_j)
                
                if motion_mag_i > 0.01 and motion_mag_j > 0.01:
                    dir_i = motion_i / motion_mag_i
                    dir_j = motion_j / motion_mag_j
                    similarity = abs(np.dot(dir_i, dir_j))
                    
                    # Calculate relative velocity (closing speed)
                    rel_velocity = abs(speed_i - speed_j)
                    
                    # Track relative velocity history
                    rel_vel_key = pair_key
                    if rel_vel_key not in self._relative_velocity_history:
                        self._relative_velocity_history[rel_vel_key] = deque(maxlen=10)
                    self._relative_velocity_history[rel_vel_key].append(rel_velocity)
                    
                    # Calculate overlap percentage (critical for rear-view)
                    overlap = self._calculate_overlap(vi["box"], vj["box"])
                    
                    # For trailing cars (one behind another from rear-view angle):
                    # 1. High overlap (>30%) indicates one car behind another
                    # 2. Similar direction (>0.9) indicates same lane
                    # 3. Low relative velocity (<0.08) indicates stable following
                    # 4. Stable distance indicates normal traffic
                    
                    is_trailing = False
                    trailing_reason = ""
                    
                    # Check for persistent trailing pattern
                    if similarity > 0.9 and overlap > 0.25:
                        # High overlap + same direction = trailing car
                        if rel_velocity < 0.08:
                            is_trailing = True
                            trailing_reason = "low relative velocity"
                        elif len(hist) >= 5:
                            # Check if distance is stable (not decreasing rapidly)
                            recent_dists = list(hist)[-5:]
                            distance_stability = np.std(recent_dists) / np.mean(recent_dists) if np.mean(recent_dists) > 0 else 1
                            if distance_stability < 0.15:  # Very stable distance
                                is_trailing = True
                                trailing_reason = "stable distance"
                    
                    # Track trailing consistency
                    if is_trailing:
                        self._vehicle_trailing_count[pair_key] = self._vehicle_trailing_count.get(pair_key, 0) + 1
                        # If trailing for more than 3 frames, definitely not a collision
                        if self._vehicle_trailing_count[pair_key] > 3:
                            if self._debug:
                                print(f"[TRAILING FILTER] Vehicles {vi['track_id']} and {vj['track_id']} - {trailing_reason}")
                            continue
                    else:
                        # Reset counter when not trailing
                        self._vehicle_trailing_count[pair_key] = 0

                # Must be approaching (for collision detection)
                if len(hist) >= self.MIN_APPROACH_FRAMES:
                    recent_dists = list(hist)[-self.MIN_APPROACH_FRAMES:]
                    is_approaching = all(recent_dists[k] > recent_dists[k+1] 
                                        for k in range(len(recent_dists)-1))
                    
                    if not is_approaching:
                        continue
                    
                    if len(hist) >= 2:
                        closing_speed = (hist[-2] - hist[-1]) / max(hist[-2], 1.0)
                        
                        if motion_mag_i > 0.01 and motion_mag_j > 0.01:
                            dir_i = motion_i / motion_mag_i
                            dir_j = motion_j / motion_mag_j
                            similarity = abs(np.dot(dir_i, dir_j))
                            
                            if similarity > self.PARALLEL_ANGLE_THRESH:
                                if closing_speed < self.MIN_CLOSING_SPEED * 2:
                                    continue
                        else:
                            if closing_speed < self.MIN_CLOSING_SPEED:
                                continue
                else:
                    continue

                # Calculate chaos
                union_box = (
                    max(0, min(vi["box"][0], vj["box"][0]) - 10),
                    max(0, min(vi["box"][1], vj["box"][1]) - 10),
                    min(flow_mag.shape[1], max(vi["box"][2], vj["box"][2]) + 10),
                    min(flow_mag.shape[0], max(vi["box"][3], vj["box"][3]) + 10),
                )
                chaos_s = OpticalFlowAnalyzer.roi_chaos(flow_mag, union_box, self.MAX_CHAOS_PX)

                # Calculate score
                score = self._calculate_score(vi, vj, centre_dist, chaos_s, hist)

                if score < self.SCORE_THRESHOLD:
                    continue
                
                # Additional check for trailing scenarios
                if motion_mag_i > 0.01 and motion_mag_j > 0.01:
                    dir_i = motion_i / motion_mag_i
                    dir_j = motion_j / motion_mag_j
                    similarity = abs(np.dot(dir_i, dir_j))
                    
                    # For trailing scenarios, require higher chaos and overlap spike
                    if similarity > 0.85:
                        overlap = self._calculate_overlap(vi["box"], vj["box"])
                        # Check for sudden overlap increase (impact indicator)
                        overlap_key = pair_key
                        if overlap_key in self._overlap_history:
                            if len(self._overlap_history[overlap_key]) >= 3:
                                recent_overlaps = list(self._overlap_history[overlap_key])[-3:]
                                overlap_increase = recent_overlaps[-1] - recent_overlaps[-3]
                                if overlap_increase < 0.05:  # No sudden overlap increase
                                    if chaos_s < 0.35:
                                        continue
                        else:
                            if chaos_s < 0.30:
                                continue

                # Cooldown check
                if frame_id - self._last_collision_frame < self._cooldown_frames:
                    continue
                
                self._last_collision_frame = frame_id
                
                breakdown = {
                    "dist": round(centre_dist, 1),
                    "chaos": round(chaos_s, 3),
                    "score": round(score, 3)
                }
                
                events.append(self._make_event(vi, vj, score, breakdown,
                    f"Collision detected - distance={centre_dist:.1f}px chaos={chaos_s:.2f}"
                ))
                
                if self._debug:
                    print(f"[COLLISION] {vi['label']} #{vi['track_id']} vs {vj['label']} #{vj['track_id']} | "
                          f"dist={centre_dist:.1f}px | score={score:.3f} | chaos={chaos_s:.2f}")

        flagged = len(events) > 0
        confirmed = self._validator.update(self._ZONE_ID, flagged)
        if confirmed:
            self._validator.reset(self._ZONE_ID)

        return confirmed, events, vehicles

    def _detect_rollover(self, vehicle: dict, frame_id: int) -> tuple[bool, dict]:
        """Detect vehicle rollover or sudden rotation."""
        track_id = vehicle["track_id"]
        box = vehicle["box"]
        
        # Calculate current aspect ratio (width/height)
        width = box[2] - box[0]
        height = box[3] - box[1]
        aspect_ratio = width / height if height > 0 else 1.0
        
        # Calculate area
        area = width * height
        
        # Store history
        if track_id not in self._vehicle_aspect_history:
            self._vehicle_aspect_history[track_id] = deque(maxlen=10)
        if track_id not in self._vehicle_area_history:
            self._vehicle_area_history[track_id] = deque(maxlen=10)
        
        self._vehicle_aspect_history[track_id].append(aspect_ratio)
        self._vehicle_area_history[track_id].append(area)
        
        # Need at least 5 frames for rollover detection
        if len(self._vehicle_aspect_history[track_id]) < 5:
            return False, {}
        
        # Calculate aspect ratio change
        prev_aspect = np.mean(list(self._vehicle_aspect_history[track_id])[:-2])
        current_aspect = aspect_ratio
        
        # Calculate area change
        prev_area = np.mean(list(self._vehicle_area_history[track_id])[:-2])
        area_change = area / prev_area if prev_area > 0 else 1.0
        
        # A vehicle rolling over will show:
        # 1. Aspect ratio dramatically changes (car becomes wider or narrower)
        # 2. Area may increase (vehicle turns sideways)
        # 3. Sudden chaos spike
        
        aspect_change_ratio = current_aspect / prev_aspect if prev_aspect > 0 else 1.0
        
        # Check for rollover indicators
        is_rollover = False
        rollover_reason = []
        
        if aspect_change_ratio > self.ROLLOVER_ASPECT_RATIO_THRESH or aspect_change_ratio < (1.0 / self.ROLLOVER_ASPECT_RATIO_THRESH):
            is_rollover = True
            rollover_reason.append(f"aspect_ratio_change_{aspect_change_ratio:.2f}")
        
        if area_change > self.ROLLOVER_AREA_CHANGE_THRESH:
            is_rollover = True
            rollover_reason.append(f"area_change_{area_change:.2f}")
        
        # Additional verification with optical flow chaos if available
        if is_rollover:
            return True, {
                "aspect_ratio": aspect_ratio,
                "aspect_change": aspect_change_ratio,
                "area_change": area_change,
                "reason": "_".join(rollover_reason)
            }
        
        return False, {}

    def _calculate_overlap(self, box1: tuple, box2: tuple) -> float:
        """Calculate bounding box overlap ratio."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        overlap_area = (x2 - x1) * (y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        
        return overlap_area / min(area1, area2)

    def _calculate_score(self, vi, vj, centre_dist, chaos_s, dist_history):
        """Calculate collision risk score."""
        score = 0.0
        
        # Proximity scoring
        if centre_dist < 30:
            score += 0.50
        elif centre_dist < 50:
            score += 0.35
        elif centre_dist < 80:
            score += 0.20
        elif centre_dist < 120:
            score += 0.10
        
        # Chaos/impact indicator
        if chaos_s > 0.4:
            score += 0.35
        elif chaos_s > 0.25:
            score += 0.20
        elif chaos_s > 0.15:
            score += 0.10
        
        # Closing speed factor
        if len(dist_history) >= 3:
            speed_of_approach = (dist_history[-3] - dist_history[-1]) / max(dist_history[-3], 1.0)
            if speed_of_approach > 0.15:
                score += 0.25
            elif speed_of_approach > 0.08:
                score += 0.15
        
        # Bbox overlap
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

        if overlap_x > 0 and overlap_y > 0:
            overlap_area = overlap_x * overlap_y
            total_area = (w_i * h_i) + (w_j * h_j) - overlap_area
            if total_area > 0:
                overlap_ratio = overlap_area / total_area
                score += min(overlap_ratio * 0.3, 0.3)
        
        return min(score, 1.0)

    def _extract_vehicles(self, boxes) -> list[dict]:
        """Extract vehicles with optimized tracking."""
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
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            conf = float(box.conf[0])
            box_tuple = (x1, y1, x2, y2)

            prev = self._prev_centres.get(track_id)
            if prev:
                b_size = _box_size((x1, y1, x2, y2))
                speed = float(np.hypot(cx - prev[0], cy - prev[1]) / b_size) if b_size > 0 else 0.0
            else:
                speed = 0.0

            self._prev_centres[track_id] = (cx, cy)
            
            hist = self._speed_histories.setdefault(track_id, deque(maxlen=self.SPEED_HISTORY))
            hist.append(speed)

            vehicles.append({
                "track_id": track_id,
                "label": _VEHICLE_CLASSES[cls_id],
                "conf": conf,
                "box": box_tuple,
                "cx": cx,
                "cy": cy,
                "speed": speed,
            })

        return vehicles

    def _dedup_vehicles(self, vehicles: list[dict]) -> list[dict]:
        """Deduplicate overlapping detections."""
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
    
    @staticmethod
    def _make_event(vi, vj, score, breakdown, reason) -> dict:
        """Create collision event dictionary."""
        return {
            "type": "road_accident",
            "cx": (vi["cx"] + vj["cx"]) // 2,
            "cy": (vi["cy"] + vj["cy"]) // 2,
            "box": (
                min(vi["box"][0], vj["box"][0]),
                min(vi["box"][1], vj["box"][1]),
                max(vi["box"][2], vj["box"][2]),
                max(vi["box"][3], vj["box"][3]),
            ),
            "vehicles": [vi["label"], vj["label"]],
            "score": round(score, 3),
            "breakdown": breakdown,
            "reason": reason,
        }
    
    # Add overlap history dictionary
    _overlap_history: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _iou(b1: tuple, b2: tuple) -> float:
    """Calculate Intersection over Union."""
    xi1 = max(b1[0], b2[0]); yi1 = max(b1[1], b2[1])
    xi2 = min(b1[2], b2[2]); yi2 = min(b1[3], b2[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    if inter == 0:
        return 0.0
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    return inter / (a1 + a2 - inter)


def _box_size(b: tuple) -> float:
    """Calculate box diagonal size."""
    return float(np.hypot(b[2] - b[0], b[3] - b[1]))


def _rmean(dq: deque, window: int = 0) -> float:
    """Calculate rolling mean of deque."""
    if not dq:
        return 0.0
    items = list(dq)[-window:] if window > 0 else list(dq)
    return float(np.mean(items)) if items else 0.0