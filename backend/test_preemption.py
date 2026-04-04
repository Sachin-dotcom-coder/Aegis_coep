import requests
import time

BASE_URL = "http://127.0.0.1:8000"

print("--- TESTING PREEMPTION LOGIC ---\n")

# 1. Dispatch a LOW priority incident
print("1) Generating Low-Priority Incident (Severity 1 Road Accident)...")
low_incident = {
    "id": "INC-TEST-LOW-01",
    "zone_id": "Z1",
    "zone_accident_frequency": 0.9,
    "type": "road_accident",
    "severity": 1,
    "camera_id": "CAM-01",
    "camera_coverage": 100,
    "people_in_frame": 1,
    "lat": 18.5300 + 0.05, # Near station A
    "lng": 73.8500 + 0.05,
    "detect_confidence": 0.95,
    "timestamp": "2026-04-01T12:00:00"
}
try:
    r1 = requests.post(f"{BASE_URL}/incidents/", json=low_incident)
    print(f"   Status Code: {r1.status_code}")
    print(f"   Response: {r1.json()}\n")
except Exception as e:
    print("Is the server running on port 8000? Error:", e)

# Wait a few seconds for the fleet tick to pick it up and assign a drone
print("2) Waiting 3 seconds for drone to deploy...")
time.sleep(3)

# 2. Dispatch a HIGH priority incident to trigger Preemption
print("3) Generating High-Priority Incident (Severity 10 Fire) to preempt the drone...")
high_incident = {
    "id": "INC-TEST-HIGH-02",
    "zone_id": "Z1",
    "zone_accident_frequency": 0.9,
    "type": "fire",
    "severity": 10,
    "camera_id": "CAM-01",
    "camera_coverage": 100,
    "people_in_frame": 50,
    "lat": 18.5300 + 0.08,
    "lng": 73.8500 + 0.08,
    "detect_confidence": 0.95,
    "timestamp": "2026-04-01T12:00:05"
}

r2 = requests.post(f"{BASE_URL}/incidents/", json=high_incident)
print(f"   Status Code: {r2.status_code}")
print(f"   Response: {r2.json()}\n")

print("Check your terminal running 'uvicorn' to perfectly watch the drone get pulled off the low-priority job and preemptively assigned to the massive fire!")
