import requests, json

payload = {"id": "INC-NEW-005", "zone_id": "Z1", "zone_accident_frequency": 0.9, "type": "road_accident", "severity": 7.5, "camera_id": "CAM-12", "camera_coverage": 1000, "people_in_frame": 45, "lat": 21.171, "lng": 72.833, "detect_confidence": 0.88, "timestamp": "2026-04-04T12:30:00"}
r = requests.post("http://127.0.0.1:8000/incidents/", json=payload)
try:
    res = r.json()
    with open("test_err_out.txt", "w") as f:
        f.write(str(res.get("traceback", res)))
except Exception as e:
    with open("test_err_out.txt", "w") as f:
        f.write("Failed to parse JSON: " + str(e) + "\n" + r.text)
