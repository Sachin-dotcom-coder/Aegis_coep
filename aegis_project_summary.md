# AegisAI — Full Project Deep-Dive Reference
### *Complete Summary for NotebookLM Presentation*

---

## 🔷 Executive Summary

**AegisAI** is a fully-integrated, autonomous emergency response system for urban environments. It connects three independent but tightly coupled layers:

1. **Detection Layer** — Real-time CCTV video analysis using computer vision (YOLO + OpenCV + Optical Flow)
2. **Backend Layer** — FastAPI autonomous drone dispatch engine with MongoDB persistence and WebSocket telemetry
3. **Frontend Layer** — Interactive React/Leaflet tactical operations dashboard for human operator oversight

The city of **Pune, India** is used as the geographic canvas. 5 drone stations across Pune host 15 drones (3 per station). 25 CCTV camera nodes are spread across the entire operational boundary. When a camera detects a critical event, an incident report is generated, prioritized, and a drone is autonomously dispatched — all in under 1 second.

---

## 🔷 PART 1: Detection System (The AI Brain)

### 1.1 Overview

The detection module (`/detection/`) is a **standalone Python application** that can run on any machine with camera access. It reads video frames (from a file or a live camera stream), runs multiple AI models in sequence, and POSTs confirmed incident reports to the FastAPI backend via REST API.

**Entry point:** `detection/run.py`
**Core brain:** `detection/detector.py` (class: `Detector`)
**Model used for human pose:** `yolov8n-pose.pt` (lightweight nano pose model)
**Model used for vehicles/weapons:** `yolov8s.pt` (small general model — better accuracy)
**Model used for vehicle tracking:** Same `yolov8s.pt` with ByteTrack algorithm

---

### 1.2 The Frame Processing Pipeline (`detector.process_frame()`)

Every single video frame passes through **6 sequential stages** in this exact order:

```
Frame IN
   │
   ▼
[Stage 0] SceneCutDetector.update(frame)
          → If SCENE CUT: Soft-reset all trackers, return early
   │
   ▼
[Stage 1] YOLOv8-Pose → Person detection + 17 Keypoint Fall Analysis
          → FrameValidator (5 consecutive flagged frames = confirmed fall)
          → CrowdAnomalyDetector feeds on velocities
   │
   ▼
[Stage 2] FireDetector.detect(frame)
          → HSV color thresholding + 8-frame flicker gate
   │
   ▼
[Stage 3] AccidentDetector.detect(frame, frame_id)
          → YOLOv8s ByteTrack + Optical Flow + Trailing/Rollover filters
   │
   ▼
[Stage 4] ImpactFlashDetector.detect(frame)
          → Pixel luminance spike analysis (catches crashes YOLO misses)
   │
   ▼
[Stage 5] Incident construction → POST to Backend API
          → Global per-type cooldown (150 frames = 5 seconds)

Frame OUT (annotated)
```

---

### 1.3 Scene Cut Detector (Unique Innovation #1)

**Purpose:** Compiled CCTV footage and dashcam video mashups contain hard video cuts between clips. Without this detector, every cut would be interpreted as a massive sudden movement (false positive explosion).

**How it works:**
1. Converts consecutive frames to grayscale, computes `cv2.absdiff()` per pixel
2. Calculates `mean_diff` across entire frame
3. If `mean_diff < 25.0` → normal motion, pass through
4. If suspicious, splits the frame into a **3×3 grid of 9 regions** and measures movement uniformity
5. Sorts regional means, discards the **3 most static** (fixed CCTV timestamps/watermarks) 
6. Calculates `uniformity = reg_min[3] / reg_max[-1]`
7. If `uniformity >= 0.45` → motion is spatially uniform across the frame → **SCENE CUT**

**On detection:** Soft-reset is called. All optical flow buffers and validation counters are cleared so phantom tracking cannot occur. Critically, YOLO tracking IDs are preserved to prevent flicker (person 3 doesn't suddenly re-appear as person 7 after the cut).

---

### 1.4 Fall Detection (YOLOv8-Pose + COCO Keypoints)

**Model:** `yolov8n-pose.pt` — generates 17 skeleton keypoints per detected person in COCO format.

**Key keypoints used:**
- `KP_LEFT_SHOULDER = 5`, `KP_RIGHT_SHOULDER = 6`
- `KP_LEFT_HIP = 11`, `KP_RIGHT_HIP = 12`

**Algorithm:**
1. For each detected person, select the **best-confidence shoulder** and **best-confidence hip** keypoint (conf must be > 0.35)
2. Measure `shoulder_y` and `hip_y` (pixel Y positions on screen)
3. **Relative threshold** — divide by the bounding box height:
   ```
   dy_relative = abs(shoulder_y - hip_y) / bbox_height
   ```
4. If `dy_relative < 0.22` → person is **horizontal** (fallen)

**Why relative, not absolute pixels?**
A person 5 meters from camera has a 50px bounding box. A person 2 meters away has 200px. Absolute pixel thresholds would fail. The 22% relative threshold scales correctly for any detection distance.

**FrameValidator** — must be flagged **5 consecutive frames** (NOT just once) before "fall confirmed" is fired. Prevents single-frame keypoint estimation errors from triggering alerts. After confirmation, that person gets a **150-frame cooldown** (5 seconds at 30fps) so one fall doesn't spam 150 incident reports.

---

### 1.5 Fire Detector (OpenCV HSV + Flicker Gate)

**Why not YOLO for fire?** YOLO is trained on still images of fire but fails on blurry CCTV footage, overexposed regions, and orange/red clothing. A pure color-space approach is more reliable.

**HSV Ranges targeting fire wavelengths:**
```python
_LOWER_A = [5,  140, 170]   # Hue 5–25 (orange-yellow fire core)
_UPPER_A = [25, 255, 255]
_LOWER_B = [165, 140, 170]  # Hue 165–180 (red outer flame)
_UPPER_B = [180, 255, 255]
```

**Detection algorithm:**
1. Convert frame to HSV → bitwise OR of two hue masks (orange + red)
2. Morphological operations (Open → Close with elliptical kernel) to remove noise
3. Find contours. Filter: `area > 5,000 pixels` AND `mean brightness > 170`
4. Track `total_area` in a rolling history of 12 frames
5. **Flicker Gate:** `std(area_history) > 300` — real fire flickers; static lights (brake lights, red shirts) have near-zero area variance
6. **FrameValidator** requires 8 confirmed frames before firing the incident alert

---

### 1.6 Accident Detector (Unique Innovation #2 — 4-Signal Fusion)

This is the most complex detector. It fuses **4 independent signals** to produce a collision risk score.

**Components used:**
- `YOLOv8s` in tracking mode with `ByteTrack` — generates stable vehicle IDs across frames
- `OpticalFlowAnalyzer` — Farneback dense optical flow for motion chaos measurement

**Vehicle Classes tracked:** `{2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}`

**Signals per vehicle pair:**
| Signal | Meaning | Weight |
|--------|---------|--------|
| `centre_dist` | Euclidean distance between bounding box centers | Proximity gate |
| `closing_speed` | Rate of distance decrease between frames | Approach validation |
| `chaos_s` | `std(optical_flow)` in the union bounding box area | Chaos/impact indicator |
| `direction_similarity` | Dot product of normalized motion vectors | Trailing car filter |

**Score Calculation:**
```
score = weighted_combination(proximity, approach_rate, chaos, direction)
if score >= 0.58 → COLLISION FLAG → FrameValidator
```

**Trailing Car False Positive Fix (Unique Innovation #3):**
CCTV cameras mounted at angles to roads create a depth-perspective problem: two cars overtaking each other or following each other in the same lane appear to significantly overlap. Standard YOLO detectors would flag this as a crash every time.

AegisAI's fix:
1. Calculate `direction_similarity = |dot(motion_vec_A, motion_vec_B)|`
2. If `similarity > 0.9` (nearly parallel motion) AND bounding box `overlap > 25%` → potential trailing situation
3. Measure `relative_velocity = |speed_A - speed_B|`
4. If `relative_velocity < 0.08` → stable following distance → **is_trailing = True**
5. Track trailing status counter. If `trailing_count > 3 consecutive frames` → **skip collision scoring entirely**
6. An actual collision would spike the relative velocity and chaos rapidly → `trailing_count` resets to 0 → collision scoring activates normally

**Vehicle Rollover/Rotation Detection (Unique Innovation #4):**
High-speed impacts often cause vehicles to rotate/flip. YOLO loses them mid-flip. AegisAI catches this via:
1. Track bounding box **aspect ratio** (width/height) per vehicle across frames
2. Track **bounding box area** across frames
3. If `current_aspect_ratio / historical_mean_aspect_ratio > 1.8` AND `area_change > 2.5x` → **ROLLOVER detected**
4. Generates an incident with `score = 0.95` (maximum severity) regardless of inter-vehicle scoring

---

### 1.7 Impact Flash Detector (Caught-What-YOLO-Missed)

**Why it exists:** At the moment of impact in a high-speed crash, debris, dust, and glass fragments scatter everywhere. YOLO loses all vehicle bounding boxes instantly (objects are destroyed/occluded). The incident would go undetected for several frames, potentially losing the critical first-report advantage.

**How it works:**
1. Uses raw pixel brightness comparison between consecutive frames
2. `mean_diff = mean(abs(gray_frame - prev_gray_frame))`
3. Validates: `8.0 < mean_diff < 50.0` (real crash, not scene cut or darkness)
4. Checks `affected_ratio = bright_pixels / total_pixels > 0.08` (8% of pixels must change)
5. Spatial uniformity check: `uniformity = region_min / region_max < 0.70` (change must be localized, NOT uniform, which would be a lighting change)
6. On confirmation → reports `road_accident` at the flash epicenter

---

### 1.8 Crowd Anomaly Detector (IsolationForest ML)

**Class:** `CrowdAnomalyDetector` in `detection/confidence.py`
**Algorithm:** sklearn `IsolationForest` (unsupervised anomaly detection)

**Input per frame:** list of `(vx, vy)` velocity vectors for every detected person

**Feature vector per frame:**
```python
feature = [mean_velocity_magnitude, max_velocity_magnitude, crowd_density]
```
- `crowd_density = people_in_frame / (frame_area / 10000)`

**Training:** Self-supervised on rolling 200-frame window. After 30 "warm-up" frames, the model has learned what "normal" crowd movement looks like for this specific scene.

**Output:** `anomaly_score ∈ [0, 1]`
- `0` = perfectly normal crowd behavior
- `1` = highly anomalous (panic, stampede, sudden scatter)

The IsolationForest internally scores samples: more negative `score_samples()` → more anomalous. Normalization: `normalised = clip(score * -1 + 0.5, 0, 1)`

**Effect:** The anomaly score feeds directly into the confidence blending formula, boosting final incident confidence during crowd panic situations.

---

### 1.9 Confidence Blending Formula

**Function:** `blend_confidence(yolo_conf, zone_accident_frequency, anomaly_score)` in `confidence.py`

```
detect_confidence = (0.50 × yolo_conf) + (0.30 × zone_accident_frequency) + (0.20 × anomaly_score)
```

- **50% YOLO confidence** — raw model detection certainty
- **30% zone frequency** — historical accident frequency in this camera zone (hotter zone = inherently more dangerous = boost confidence)
- **20% anomaly score** — crowd misbehavior amplifier

Result is clamped to `[0.0, 1.0]` and becomes `detect_confidence` in the incident payload.

---

### 1.10 Dynamic Severity Calculation

**Function:** `Detector._calculate_severity()` in `detector.py`

Base severity values:
```python
SEVERITY_MAP = {
    "fallen_person": 6.0,
    "fire":          8.5,
    "road_accident": 7.5,
    "gun_fired":     9.5,
}
```

**Multiplier chain:**
```
severity = base_severity × area_factor × zone_factor × crowd_factor × rotation_factor × speed_factor
```

| Factor | How calculated |
|--------|---------------|
| **area_factor** | Fire: normalized `area/30000` → scales 0.5–1.0. Accident: normalized `area/20000` → scales 0.6–1.0 |
| **zone_factor** | `1.0 + (zone.accident_frequency × 0.4)` → range 1.0–1.4 |
| **crowd_factor** | `1.0 + min(0.2, people_in_frame × 0.02)` → range 1.0–1.2 |
| **rotation_factor** | If vehicle rotated detected: `1.4` (+40%) |
| **speed_factor** | If max vehicle speed `> 0.5`: `1.0 + min(0.5, (max_speed - 0.5) × 0.5)` → up to +25% |

Final severity is clamped to `[1.0, 10.0]`.

---

### 1.11 Geo-Mapping: Pixel → Latitude/Longitude

**File:** `detection/geo_mapper.py`

The frontend Leaflet map requires real-world coordinates. The detection system works in pixel-space. The geo-mapper bridges this gap.

**Design decision:** All incidents from the same camera get the **camera's fixed GPS coordinates** as their location (not a per-pixel interpolation). This is physically correct: you know *which camera* saw the event, and that camera has a known real-world location. 

**Zone grid:** The 640×480 frame is divided into a 2×2 grid (4 zones: Z1–Z4), each with a historical accident frequency value (0.3 to 0.7). The pixel position `(cx, cy)` determines which zone (and thus which zone metadata) is attached to the incident.

**Camera registry:**
```python
CAMERA_LOCATIONS = {
    "CAM-01": (18.5204, 73.8567),  # Shivajinagar / Pune Station
    "CAM-02": (18.5800, 73.7500),  # Baner/Balewadi
    "CAM-03": (18.5600, 73.9100),  # Viman Nagar
    "CAM-04": (18.4600, 73.8400),  # Katraj
}
```

---

### 1.12 Global API Cooldown (Spam Prevention)

A critical operational safeguard. Without it, a 5-second fire clip at 30fps would POST 150 identical `fire` incidents to the backend, flooding the database.

```python
self._type_cooldown = {"fire": 0, "road_accident": 0, "gun_fired": 0}
# After each confirmed POST:
self._type_cooldown["fire"] = 150  # 5 seconds at 30fps
```

Each frame, all cooldown values decrement by 1. A new incident of a given type can only post when its cooldown reaches 0.

---

## 🔷 PART 2: Backend (Autonomous Dispatch Engine)

### 2.1 Stack and Architecture

- **Framework:** FastAPI (async Python)
- **Database:** MongoDB Atlas (cloud) with `motor` async driver
- **Real-time:** WebSockets (native FastAPI) for drone telemetry push
- **Startup/Shutdown:** `asynccontextmanager` lifespan manager
- **Simulation:** Pure Python async loop running at 1Hz (1 tick/second)

**API Routes:**
- `GET/POST /incidents/` — incident management
- `GET /drones/` — current fleet snapshot
- `GET /audits/` — activity log
- `WS /ws/drones` — WebSocket stream for real-time telemetry

---

### 2.2 Server Startup Sequence (Critical — Persistence)

On startup (`main.py lifespan()`):
1. Connect to MongoDB Atlas
2. Query `db.incidents.find({status: {$in: ["queued", "in_progress", "auto", "en_route"]}})`
3. For any `en_route` mission (from before restart): reset status back to `"auto"`, clear `assigned_drone`
4. Push all these incidents back into `fleet.pending_queue`
5. Launch the `fleet.run()` async task

**Why this matters:** If the server crashes mid-mission, drones would be "in flight" in the database with no backend to manage them. On restart, the system re-adopts all pending work. The drone dispatch queue rebuilds itself from persistent state automatically.

---

### 2.3 Drone Fleet State Machine

**15 drones total** — 3 per station, 5 stations across Pune:
```python
stations = [
    (18.6200, 73.8300),  # Station 1 - North
    (18.5600, 73.9400),  # Station 2 - East
    (18.5900, 73.7400),  # Station 3 - West
    (18.4600, 73.8500),  # Station 4 - South
    (18.4500, 73.7000),  # Station 5 - Southwest
]
```

**State machine per drone:**
```
IDLE ──────────────────────────────────────▶ EN_ROUTE (dispatched to incident)
 ▲                                                │
 │ battery >= 100%                               ▼
CHARGING ◀── battery < 100% + at station    ON_SCENE (dwell_timer = 15 ticks)
                                                  │
                        RECALLED ◀───────────────◀ (task complete or abort)
                            │
                            ▼
                        IDLE (after arriving at station)
```

**Tick execution (every 1 second):**
1. Idle drones at stations with `battery < 100%` → transition to `CHARGING`
2. Idle drones not at stations → `trigger_recall()` (return home)
3. All drones call `drone.tick()` → physics simulation step
4. Process events returned from tick (`DRONE_ON_SCENE`, `DRONE_TASK_COMPLETE`)
5. Call `fleet.process_queue()` → dispatch from pending queue
6. Broadcast JSON fleet state to all WebSocket clients

---

### 2.4 Physics Simulation (Drone.tick() and _move_toward())

**Constants:**
```python
BATTERY_DRAIN_RATE = 0.2    # % per second when flying
BATTERY_CHARGE_RATE = 0.4   # % per second when charging
DRONE_SPEED_LATLNG = 0.0015 # degrees per second (~167m/s scaled to map)
```

**Movement per tick:**
```python
dlat = target_lat - drone.lat
dlng = target_lng - drone.lng
dist = sqrt(dlat² + dlng²)
next_lat = drone.lat + (dlat / dist) * DRONE_SPEED_LATLNG
next_lng = drone.lng + (dlng / dist) * DRONE_SPEED_LATLNG
```

**No-fly zone avoidance (collision avoidance):**
Before committing to `next_lat/next_lng`:
1. Check `is_in_nfz(next_lat, next_lng)` — if inside any restricted circle
2. Check inter-drone separation: `distance_to_other_drone < 0.0005°` (50 meter exclusion bubble)
3. If blocked: try 6 rotation angles `[45°, -45°, 90°, -90°, 135°, -135°]` to find a clear path
4. If all angles blocked: **hover in place** (never enter NFZ)

---

### 2.5 No-Fly Zone Path Cost Expansion (Unique Algorithm)

**Function:** `get_nfz_aware_distance(p1, p2)` used for ETA and battery calculations.

Standard Euclidean distance is WRONG if the direct path crosses a restricted airspace zone. Instead:

For each NFZ circle `(cx, cy, r)`:
1. Calculate perpendicular distance from NFZ center to the route line using area formula:
   ```
   area = |(p2.lat - p1.lat)(cy - p1.lat) - (p1.lat - cx)(p2.lng - p1.lng)|
   h = area / line_length
   ```
2. If `h < r` (NFZ intersects route line):
   - Verify NFZ is actually between p1 and p2 (dot product projection test)
   - Calculate the chord through the circle: `chord = 2 * sqrt(r² - h²)`
   - Replace the chord with the actual arc: `arc = r × 2 × arcsin(chord / (2r))`
   - Add `(arc - chord)` to the total path expansion
3. Return `euclidean_distance + total_expansion`

This gives a **physically realistic ETA and battery estimate** that accounts for the drone actually flying around restricted zones.

---

### 2.6 Dynamic Priority Queue (The Dispatch Brain)

**Formula:** `calculate_dynamic_priority(incident, distance_to_drone)`

```
Score = (Severity × CrowdFactor × DetectConfidence × TimeWeight × RecencyBoost × MultiCamBonus)
        ─────────────────────────────────────────────────────────────────────────────────────────
                                    (1 + ETA_Penalty)
```

| Component | Formula | Effect |
|-----------|---------|--------|
| **Severity** | `incident.severity` (1.0–10.0) | Base incident importance |
| **CrowdFactor** | `1.0 + people_in_frame / 100.0` | More people = higher urgency |
| **DetectConfidence** | `incident.detect_confidence` | Uncertain detections rank lower |
| **TimeWeight** | `1.3` if nighttime (20:00–06:00 UTC), else `1.0` | Night events are harder to respond to manually |
| **RecencyBoost** | `1.2` if incident < 2 minutes old, else `1.0` | Fresh incidents get priority over stale queue items |
| **MultiCamBonus** | `incident.multi_cam_bonus` (default 1.0) | Multiple cameras confirming same incident → higher confidence |
| **ETA_Penalty** | `distance_to_best_drone × 100.0` | Far-away drones are penalized — use closer fleet instead |

**Queue sorting:** After each new incident or dispatch, the entire pending queue is re-sorted by this score (descending). The highest-scoring incident always dispatches first.

---

### 2.7 Swarm Prevention (Spatial Deduplication)

When multiple near-simultaneous reports arrive for the same incident (e.g., 3 consecutive video frames all POST the same fire):

**In `process_queue()`:**
```python
for each active en_route/on_scene drone:
    coverage_dist = sqrt((drone.target_lat - incident_lat)² + (drone.target_lng - incident_lng)²)
    if coverage_dist < 0.002°:   # ~200 meters
        already_covered = True
```
If covered: incident status set to `"merged"` in MongoDB and removed from queue. **No swarm.**

---

### 2.8 Mission Hijack Protocol

If the best available drone is already `EN_ROUTE` to a lower-priority incident, it can be re-tasked:

```python
if best_drone.state == DroneState.EN_ROUTE:
    if new_incident.priority_score < best_drone.assigned_priority + 2:
        continue   # Not worth the diversion
    # Otherwise: HIJACK
    best_drone.dispatch(new_target)  # Overwrite target mid-flight
```

The `+2` buffer prevents thrashing (drone doesn't keep swapping targets for marginal priority differences). The original incident returns to the pending queue for possible reassignment.

---

### 2.9 Battery Safety Check

Before dispatching any drone, the system validates it has enough battery for the full round trip:

```python
req_cost = (dist_to_incident / DRONE_SPEED_LATLNG) × BATTERY_DRAIN_RATE
hover_cost = 15 × BATTERY_DRAIN_RATE     # 15 seconds on-scene dwell
return_cost = (dist_incident_to_station / DRONE_SPEED_LATLNG) × BATTERY_DRAIN_RATE

if drone.battery > (req_cost + hover_cost + return_cost): OK to dispatch
```

A drone that can reach the incident but NOT return home safely is **rejected** as a candidate.

---

### 2.10 Audit Logging System

Every significant autonomous action is logged to `db.audit` collection:

| Action | Trigger |
|--------|---------|
| `AUTO_DISPATCH` | Drone dispatched autonomously |
| `HIJACK_DISPATCH` | Mid-flight diversion to higher priority |
| `DRONE_ON_SCENE` | Drone arrives at incident → incident status → `"in_progress"` |
| `DRONE_TASK_COMPLETE` | 15-second dwell completes → incident **deleted** from active DB |
| `DRONE_ARRIVED_STATION` | Recalled drone returns to base |

All logs include `timestamp`, `action`, `incident_id`, `drone_id`, `reason`. Accessible via `GET /audits/`.

---

### 2.11 WebSocket Telemetry

**Endpoint:** `ws://localhost:8000/ws/drones`

Every 1 second, the fleet tick broadcasts a JSON array of all 15 drone telemetry objects:

```json
[{
  "drone_id": "D1",
  "state": "en_route",
  "lat": 18.5412,
  "lng": 73.8934,
  "battery": 87.4,
  "assigned_incident": "INC-0042",
  "eta_seconds": 34,
  "path_progress": 62.3,
  "charging_progress": 0
}, ...]
```

The frontend React hook `useSimulation.ts` maintains a persistent WebSocket connection and updates local state on every message push.

---

## 🔷 PART 3: Frontend (Tactical Operations Dashboard)

### 3.1 Stack

- **Framework:** React 18 + Vite (TypeScript)
- **Routing:** React Router DOM
- **Map:** Leaflet.js with custom dark-mode tile styling
- **State/Data:** TanStack React Query + custom `useSimulation` hook
- **Icons:** Lucide React
- **UI:** Vanilla CSS with custom design system (no Tailwind)

---

### 3.2 Data Models (TypeScript Interfaces in `lib/types.ts`)

```typescript
interface Drone {
  id: string;
  position: GeoPoint;
  battery: number;
  status: DroneStatus;  // 'idle' | 'en_route' | 'on_site' | 'recalled' | 'charging'
  targetIncidentId?: string;
  basePosition: GeoPoint;
  zoneId: string;
  eta_seconds?: number;
  path_progress?: number;        // 0–100% of mission completed
  charging_progress?: number;    // 0–100% battery charge level
}

interface Incident {
  id: string;
  type: IncidentType;            // 'road_accident' | 'fire' | 'gun_fired' | 'fallen_person' | ...
  position: GeoPoint;
  detectionConfidence: number;   // From CV blend_confidence formula (0–1)
  decisionConfidence: number;    // Final blended score for dispatch decision
  priorityScore: number;         // From calculate_dynamic_priority formula
  status: IncidentStatus;        // 'pending' | 'queued' | 'dispatched' | 'in_progress' | ...
  severity: number;              // 1.0–10.0
  peopleInFrame: number;
  cameraSource: string;
  multiCamBonus?: number;
}
```

---

### 3.3 CityMap Component (Interactive Digital Twin)

**File:** `frontend/src/components/CityMap.tsx`

The centerpiece of the entire UI. A **live, interactive, dark-mode map of Pune** rendered with Leaflet.

**Map modes:** 3 switchable tile layers
- **2D Standard:** OpenStreetMap with dark CSS filter (`grayscale(1) invert(1) brightness(0.4)`)
- **Satellite:** ESRI World Imagery
- **Terrain:** OpenTopoMap

**Operational overlays rendered:**
1. **25 CCTV camera markers** — distributed across maximum operational bounds
2. **5 dispatch zone markers** — labeled stations with click-to-dispatch functionality
3. **4 No-Fly Zones** — animated pulsing red restricted circles (pulse period: 3 seconds)
4. **15 drone markers** — dynamic SVG icons that:
   - **Rotate** toward their current target destination (updated every telemetry tick)
   - **Glow white** when `en_route` (pulsing ring animation)
   - **Glow red** when `on_site` (different colored ring + brighter filter)
   - **Dim** when idle or charging (opacity filter: 0.4)
5. **Active incident markers** — white circular markers pulsing for critical incidents (severity >= 8)
6. **Flowing route lines** — animated dashed polylines connecting dispatched drones to targets (CSS `stroke-dashoffset` animation)

**Drone rotation logic:**
```typescript
rotation = atan2(target.lat - drone.lat, target.lng - drone.lng) × (180 / π)
// Applied as: transform: rotate(${rotation}deg) with transition: 0.5s ease
```

**Maximized mode:** Full-screen portal rendering using React `createPortal(mapContent, document.body)` for distraction-free tactical view.

---

### 3.4 Live Feed Tactical HUD

When a drone arrives `on_site`, an animated overlay appears on the map:
> **"OBJECTIVE REACHED → Unit D3"** with a [Bridge Link] button

Clicking opens a full video overlay with a military-grade HUD:
- **4K UHD video simulation** (looping `/video.mp4` representing drone-camera feed)
- **Gimbal Pan & Tilt controls** — 4-directional arrow buttons updating CSS `translate(x, y)` on the video element
- **Optical Zoom** — + / − buttons adjusting CSS `scale(n)` from 1.0× to 4.0×, zoom-corrected pan speed
- **"Reset Gimbal"** — returns to centered 1.5× zoom
- **"Abort Mission"** — calls `onAbort(droneId)` API and closes feed
- **Maximize/Minimize** toggle for full-screen feed
- Signal bars, encrypted protocol label, REC indicator — complete tactical immersion

---

### 3.5 Decision Panel (Human-in-the-Loop Interface)

**File:** `frontend/src/components/DecisionPanel.tsx`

When an operator clicks any incident marker, the Decision Panel opens. It shows the full AI reasoning breakdown for that detection:

**Action classification logic:**
```typescript
if (incident.status ∈ ['auto', 'dispatched', 'in_progress', 'en_route'])
  → "MISSION DEPLOYED" (show Recall button)
else if (incident.decisionConfidence > 0.8)
  → "AUTO DISPATCH" (system autonomous)
else if (incident.decisionConfidence >= 0.3)
  → "HUMAN CONFIRM" (operator must approve)
else
  → "LOW CONFIDENCE" (likely false positive)
```

**Priority Matrix displayed to operator:**
- Severity (raw number)
- Z-Factor (zone risk multiplier)
- Temporal weight (time of day)
- Recency boost
- Final SCORE

**Confidence bars:**
- CNN Detection confidence (from YOLO blend)
- Zone Statistics reliability
- Neural Core (decision confidence)

**Buttons:**
- **Authorize Unit** → `POST /incidents/{id}/dispatch` → drone dispatches
- **Reject Detection** → `POST /incidents/{id}/reject` → incident marked rejected, no drone wasted
- **Recall Unit** (when deployed) → `POST /drones/{droneId}/recall` → drone ordered home mid-mission

---

### 3.6 Active Missions Panel

**File:** `frontend/src/components/ActiveMissionsPanel.tsx`

Sidebar panel listing every non-idle drone with live status:
- **Status badge:** ON STATION (red pulse) / CHARGING (green) / EN_ROUTE (blue)
- **ETA countdown** for flying drones: `Xm Ys`  
- **STREAM button** for `on_site` drones → opens the Live Feed HUD
- **Progress bar** showing either Mission Progress (%) or Charge Level (%)

---

### 3.7 Drone Fleet Panel

**File:** `frontend/src/components/DroneFleetPanel.tsx`

Overview of all 15 drones grouped by station, showing battery level with color coding:
- `battery < 20%` → Red (critical)
- `20% ≤ battery < 50%` → Yellow (warning)
- `battery ≥ 50%` → Green (nominal)

---

## 🔷 PART 4: System Integration Flow

```
CCTV Camera Feed (video file or live stream)
        │
        ▼
detection/run.py  (frame-by-frame loop)
        │
        ▼
Detector.process_frame(frame)
   ├── SceneCutDetector
   ├── YOLOv8-pose (fall detection)
   ├── CrowdAnomalyDetector (IsolationForest)
   ├── FireDetector (HSV + flicker)
   ├── AccidentDetector (YOLO + ByteTrack + OpticalFlow)
   └── ImpactFlashDetector
        │
        ▼ (if confirmed incident)
POST /incidents/  [REST API to FastAPI backend]
        │
        ▼
FastAPI backend receives incident
   ├── Validates & stores in MongoDB
   ├── Calculates priority score (formula)
   ├── Adds to fleet.pending_queue
   └── Returns 201 Created
        │
        ▼
DroneFleet.process_queue() [runs every 1 second]
   ├── Spatial dedup check (swarm prevention)
   ├── Battery feasibility check
   ├── best_drone_for(lat, lng) [NFZ-aware distance scoring]
   ├── Mission Hijack check
   └── drone.dispatch() → state = EN_ROUTE
        │
        ▼
DroneFleet.run() broadcasts WebSocket telemetry
        │
        ▼
React Frontend (WS connection)
   ├── CityMap: Drone moves toward target in real-time
   ├── ActiveMissionsPanel: ETA counting down
   └── DecisionPanel: Status updates (dispatched → in_progress)
        │
        ▼ (drone arrives)
DRONE_ON_SCENE event
   ├── MongoDB: incident.status = "in_progress"  
   ├── Frontend: "Objective Reached" alert appears
   └── Operator opens Live Feed HUD
        │
        ▼ (15-second dwell)
DRONE_TASK_COMPLETE event
   ├── MongoDB: incident DELETED (auto-archived)
   ├── Audit log entry created
   ├── Drone → RECALLED → returns to nearest station
   └── Frontend: Mission marker removed from map
```

---

## 🔷 PART 5: Key Technical Innovations Summary

| Innovation | Description | Files |
|-----------|-------------|-------|
| **Scene Cut Detection** | Spatial uniformity uniformity grid prevents phantom false alarms across video cuts | `incident_detectors.py` |
| **Relative Fall Threshold** | Scale-invariant `shoulder_y/bbox_height` works at any detection range | `detector.py` |
| **Trailing Car Filter** | Direction dot product + relative velocity prevents lane-following false crashes | `incident_detectors.py` |
| **Vehicle Rollover Detection** | Aspect ratio + area spike detection catches flipped vehicles YOLO misses | `incident_detectors.py` |
| **Impact Flash Detector** | Catches crashes at moment of impact when YOLO has already lost the vehicles | `incident_detectors.py` |
| **IsolationForest Crowd AI** | Self-training unsupervised model detects panic/stampede from velocity patterns | `confidence.py` |
| **3-Signal Confidence Blend** | YOLO + Zone History + Crowd Anomaly → single weighted confidence score | `confidence.py` |
| **NFZ Arc-Expansion Distance** | Euclidean path cost corrected with circular arc math for restricted zones | `drone_fleet.py` |
| **Priority Score Formula** | Multi-factor weighted formula with time/recency/crowd/distance penalties | `priority.py` |
| **Swarm Prevention** | Spatial radius check prevents multiple drones covering the same incident | `drone_fleet.py` |
| **Mission Hijack Protocol** | In-flight drone re-tasking for priority surge events | `drone_fleet.py` |
| **Battery Round-Trip Safety** | Validates fuel for to-incident + dwell + return before dispatch acceptance | `drone_fleet.py` |
| **Startup Re-adoption** | Server restart auto-reloads pending incidents from MongoDB | `main.py` |
| **Dynamic Severity** | Area + zone + crowd + rotation + speed multipliers per incident type | `detector.py` |
| **Gimbal Pan/Tilt HUD** | CSS transform-based video pan/zoom simulating real drone camera hardware | `CityMap.tsx` |
| **Rotating Drone Icons** | Real-time SVG rotation via atan2 heading calculation toward target | `CityMap.tsx` |
| **Flowing Route Lines** | CSS stroke-dashoffset animation on Leaflet polylines | `CityMap.tsx` |

---

## 🔷 PART 6: Numbers at a Glance

| Metric | Value |
|--------|-------|
| Total drones | **15** (3 per station × 5 stations) |
| Camera nodes | **25** across Pune |
| No-fly zones | **4** (Airport, Camp, Government, South Perimeter) |
| Detection types | **6** (fall, fire, accident, gun_fired, crowd_anomaly, impact_flash) |
| Confirmation gate (fall/fire) | **5–8 consecutive frames** |
| Per-type API cooldown | **150 frames = 5 seconds** |
| Priority formula components | **7** (severity, crowd, confidence, time, recency, multi-cam, ETA) |
| Drone speed | `0.0015°/sec` per simulation tick |
| Battery drain | `0.2%/sec` when flying |
| Battery charge | `0.4%/sec` when docked |
| On-scene dwell time | **15 seconds** |
| WebSocket broadcast rate | **1 Hz** (every second) |
| MongoDB sync (queue reload) | **every 5 seconds** |

---

## 🔷 Slide Recommendations for NotebookLM PPT

1. **Title Slide** — AegisAI: Autonomous Urban Emergency Response System
2. **System Architecture Diagram** — 3-layer flow (Detection → Backend → Frontend)
3. **Detection Pipeline** — 6-stage frame processing with stage labels
4. **Fire Detection Deep Dive** — HSV ranges + flicker gate visual
5. **Accident Detection Deep Dive** — 4-signal fusion + trailing car fix flowchart
6. **Rollover + Impact Flash** — Catches what YOLO misses (unique selling points)
7. **Confidence Formula** — Pie/bar breakdown: 50% YOLO + 30% Zone + 20% Anomaly
8. **Priority Score Formula** — Full numerator/denominator equation with component labels
9. **NFZ Arc Expansion** — Visual diagram of chord vs arc path cost
10. **State Machine Diagram** — Drone lifecycle (IDLE → EN_ROUTE → ON_SCENE → RECALLED → CHARGING)
11. **Swarm Prevention + Hijack** — 200m spatial dedup + priority threshold diversion
12. **Frontend Map Screenshot** — Dark Leaflet map with drone markers, routes, incident markers
13. **Decision Panel** — Confidence bars + Priority matrix breakdown + human override buttons
14. **Live Feed HUD** — Gimbal controls, REC indicator, signal bars, tactical overlay
15. **System Integration Flow** — Full end-to-end timeline from camera frame to drone departure
16. **Innovation Summary Table** — All 17+ unique innovations in a single grid
17. **Numbers at a Glance** — Stats table for quick reference
