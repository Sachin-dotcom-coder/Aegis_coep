# AegisAI: Autonomous Urban Emergency Response System

## 1. Executive Summary
AegisAI is an integrated, state-of-the-art, autonomous urban emergency response system designed to drastically reduce response times to incidents in urban environments. Deployed conceptually in Pune, India, the system coordinates a fleet of 15 fully autonomous drones spread across 5 stations, guided by 25 CCTV camera nodes spanning the city. When an anomaly such as a fire, accident, or fallen person is detected by the AI-powered computer vision cameras, the system generates a prioritized incident report and auto-dispatches the nearest available drone—bridging the crucial gap between incident occurrence and operational readiness within less than a second.

AegisAI consists of three interconnected layers:
- **Detection System (The AI Brain):** A pure Python application using computer vision models (YOLO and OpenCV).
- **Backend Dispatch Engine:** A FastAPI service managing the drone states, dynamic priority queuing, and WebSocket telemetry.
- **Tactical Operations Dashboard:** A React-based spatial frontend map visualizing telemetry and facilitating operator decision-making.

---

## 2. The Detection Layer
The detection system is a standalone Python application that performs frame-by-frame analysis of CCTV footage to detect critical incidents. Its pipeline processes up to six sequentially fused signals and passes the findings directly to the backend.

### Core Detectors and Innovations
- **Scene Cut Detector:** Analyzes pixel-wise spatial uniformity to differentiate actual chaotic movement from hard cuts in video compilations, preventing false positives and re-initializing the tracking optical buffers.
- **Fall Detection:** Uses the `yolov8n-pose.pt` pose estimation model to extract human structural keypoints. AegisAI uses a scale-invariant ratio rather than absolute pixels, which confirms a continuous horizontal fall if tracked across five consecutive frames.
- **Fire Detector:** Replaces CNN object detection with robust OpenCV-based HSV color-space analysis that extracts fire core (orange-yellow) and edge flames (red) combined with a historical Flicker Gate to distinguish actual fire from generic red-hued objects.
- **Accident Detector:** Employs YOLO-driven tracking combined with Dense Optical Flow. The severity uses unique innovations such as a **Trailing Car Filter** (identifies parallel motion vectors to suppress false collision alerts) and **Rollover Detection** (detecting major aspect-ratio/area shifts typical of vehicle flips).
- **Crowd Anomaly Detector:** Integrates a self-supervised IsolationForest model. It observes spatial trajectory flows, extracting crowd speed and density behaviors over 200 frames. Sudden chaotic scatter translates into an anomaly confidence boost.
- **Impact Flash Detector:** Detects sudden bursts of frame luminance at times of catastrophic high-speed impact where standard tracking fails due to sudden occlusion.

To avoid alert cascades, a global per-type 150-frame cooldown prevents spamming the backend. The fused detection parameters derive a final confidence level and baseline priority score.

---

## 3. Backend Dispatch Engine
The backend serves as the orchestration engine, driven by FastAPI, MongoDB Atlas, and a persistent async simulation running at 1Hz.

### Intelligent Resource Allocation
The system runs strict logic for dynamic drone operations:
- **Spatial Swarm Prevention:** Deduplicates overlapping incident reports—drones arriving within a 200m radius merge their targets ensuring efficient asset use.
- **NFZ-Aware Distance Mapping:** Instead of simple euclidean calculation, AegisAI’s algorithm accounts for geo-fenced No-Fly Zones (NFZs) by mathematically computing a route path clearance around an intersecting restricted boundary, leading to accurate fuel ETA models.
- **Dynamic Priority Formula:** Incoming requests weigh the base severity against crowd factors, time of day, drone distance penalties, and model certitude. The queue stays dynamically sorted so the highest criticality incidents take absolute precedence.
- **Mission Hijacking:** If a catastrophic event registers while a drone is in-flight to a low-tier mission, a priority delta (+2) threshold dynamically re-assigns and diverts the drone.
- **Battery Safety Gate:** Dispatches only process if the calculated battery drain covering ingress, 15 seconds loiter-time, and auto-return successfully clears safely below the drone current charge.

The backend streams drone latitude, longitude, ETA, and battery status directly via real-time WebSockets to the connected clients and automatically resumes operations and database synchronizations even after a server crash.

---

## 4. Tactical Operations Dashboard
Operating as a Leaflet map integrated natively into React/Vite architecture, the tactical frontend presents a rich, immersive live view that supports Human-in-the-Loop interventions.

### Visualizations and Interactive Protocols
- **Digital Twin Mapping:** Real-world geo-coordinates synchronize with visual drone positions displaying pulsing vectors of flight paths spanning across a custom dark-mode tile layer map of Pune.
- **Decision Panel:** Operators clicking anomalies reveal a breakdown matrix of AI reasoning, providing granular sliders of detection logic that recommend autonomous intervention while affording operators manual Confirm, Reject, or Recall Unit authorizations.
- **Live Video Interface:** Upon drone arrival, operators invoke a custom HUD interface streaming the field video which features immersive GUI features like real-time gimbal pan & tilt mapping bound to CSS transforms spanning optical zooming options.

---

## 5. Conclusion
AegisAI successfully leverages edge-ready Computer Vision combined with a cloud-scale backend microservice to manage responsive aerial vehicles seamlessly. The integration limits operational lag time and maximizes tactical visibility during urban emergencies, ensuring optimal and rapid dispatch logic based on the contextual safety boundaries surrounding physical deployment scenarios.