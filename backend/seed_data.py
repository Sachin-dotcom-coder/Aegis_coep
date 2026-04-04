#!/usr/bin/env python3
"""
seed_data.py  —  Aegis AI sample data seeder
Populates MongoDB with realistic incidents and audit entries so the
frontend looks filled from the first load.

Usage (from the backend/ directory):
    python seed_data.py
"""

import asyncio
import datetime
import random
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URL    = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB     = os.getenv("MONGO_DB_NAME", "Aegis_AI")

# ── Sample incident data ──────────────────────────────────────────────────────
# All fields match app/models/incidents_models.py exactly.

INCIDENT_TYPES = [
    {"type": "road_accident",   "severity": 9},
    {"type": "crowd_gathering", "severity": 7},
    {"type": "fallen_person",   "severity": 8},
    {"type": "intrusion",       "severity": 6},
    {"type": "fire",            "severity": 8},
    {"type": "earthquake",      "severity": 9},
]

ZONES = [
    {"id": "Z1", "lat": 18.5300, "lng": 73.8500, "freq": 0.8, "cam": "CAM-SHV"},
    {"id": "Z2", "lat": 18.5500, "lng": 73.9300, "freq": 0.6, "cam": "CAM-VIM"},
    {"id": "Z3", "lat": 18.5900, "lng": 73.7300, "freq": 0.5, "cam": "CAM-KAT"},
    {"id": "Z4", "lat": 18.4500, "lng": 73.8600, "freq": 0.9, "cam": "CAM-SWG"},
    {"id": "Z5", "lat": 18.5600, "lng": 73.9100, "freq": 0.7, "cam": "CAM-KTH"},
]

STATUSES = ["resolved", "resolved", "resolved", "in_progress", "queued", "pending", "rejected"]

def make_incident(i: int) -> dict:
    zone     = random.choice(ZONES)
    inc_type = random.choice(INCIDENT_TYPES)
    detect   = round(random.uniform(0.45, 0.99), 2)
    zone_freq = zone["freq"] + random.uniform(-0.1, 0.1)
    decision = round(detect * zone_freq, 2)
    # Clamp to reasonable priority
    priority = round(inc_type["severity"] * decision, 3)

    # Spread timestamps over last 3 hours
    minutes_ago = random.randint(0, 180)
    ts = datetime.datetime.utcnow() - datetime.timedelta(minutes=minutes_ago)

    status = random.choice(STATUSES)

    return {
        "id":                     f"INC-{str(i).zfill(3)}",
        "zone_id":                zone["id"],
        "zone_accident_frequency": round(zone_freq, 2),
        "type":                   inc_type["type"],
        "severity":               inc_type["severity"],
        "camera_id":              f"{zone['cam']}-{random.randint(1, 9):02d}",
        "camera_coverage":        random.randint(80, 500),
        "people_in_frame":        random.randint(1, 40),
        "lat":                    round(zone["lat"] + random.uniform(-0.01, 0.01), 6),
        "lng":                    round(zone["lng"] + random.uniform(-0.01, 0.01), 6),
        "detect_confidence":      detect,
        "timestamp":              ts,
        "decision_confidence":    decision,
        "priority_score":         priority,
        "status":                 status,
        "assigned_drone":         f"D{random.randint(1,15)}" if status in ("in_progress",) else None,
        "eta_seconds":            random.randint(30, 240) if status == "in_progress" else None,
    }


def make_audit_entries(incidents: list[dict]) -> list[dict]:
    entries = []
    actions = [
        "INCIDENT_RECEIVED_AUTO", "INCIDENT_RECEIVED_HUMAN", "AUTO_DISPATCH",
        "HUMAN_OPERATOR_APPROVE", "HUMAN_OPERATOR_REJECT", "DRONE_ON_SCENE",
        "DRONE_TASK_COMPLETE", "INCIDENT_RESOLVED", "ADMIN_RECALL_DRONE",
        "PREEMPTIVE_DISPATCH",
    ]
    drone_ids = [f"D{i}" for i in range(1, 16)]

    for inc in incidents:
        # 1–4 audit entries per incident
        for _ in range(random.randint(1, 4)):
            action = random.choice(actions)
            ts_offset = random.randint(0, 60)
            ts = inc["timestamp"] + datetime.timedelta(seconds=ts_offset)
            entries.append({
                "timestamp":          ts,
                "action":             action,
                "incident_id":        inc["id"],
                "drone_id":           random.choice(drone_ids),
                "reason":             f"System trace: {action} executed by fleet.",
                "priority_score":     inc["priority_score"],
                "decision_confidence":inc["decision_confidence"],
            })

    # Also add some standalone drone events
    for _ in range(15):
        entries.append({
            "timestamp":  datetime.datetime.utcnow() - datetime.timedelta(minutes=random.randint(0, 120)),
            "action":     random.choice(["DRONE_CHARGING", "DRONE_ON_SCENE", "ADMIN_DEPLOY_DRONE"]),
            "incident_id":"N/A",
            "drone_id":   random.choice(drone_ids),
            "reason":     "System automated event.",
        })

    # Sort newest first
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries


async def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB]

    # Clear old sample data
    print("🗑  Clearing existing sample data...")
    await db.incidents.delete_many({"id": {"$regex": "^INC-"}})
    await db.audit.delete_many({"reason": {"$regex": "System"}})

    now = datetime.datetime.utcnow()

    # ── 10 heavy-load incidents (to test scrolling) ──────────────────────────
    incidents = [
        {
            "id": f"INC-00{i+1}",
            "zone_id": f"Z{(i % 5) + 1}",
            "zone_accident_frequency": 0.8,
            "type": random.choice(["road_accident", "fire", "intrusion", "fallen_person"]),
            "severity": random.randint(5, 9),
            "camera_id": f"CAM-TEST-{i}",
            "camera_coverage": 300,
            "people_in_frame": random.randint(5, 50),
            "lat": round(18.5 + (random.random() * 0.1), 4),
            "lng": round(73.8 + (random.random() * 0.1), 4),
            "detect_confidence": 0.85,
            "timestamp": now - datetime.timedelta(minutes=i*2),
            "decision_confidence": 0.75,
            "priority_score": 8.5,
            "status": "in_progress" if i < 6 else "pending",
            "assigned_drone": f"D{i+1}" if i < 6 else None,
            "eta_seconds": 30 if i < 6 else None,
        } for i in range(10)
    ]

    result = await db.incidents.insert_many(incidents)
    print(f"✅ Inserted {len(result.inserted_ids)} incidents")

    # ── Heavy load audit trail ────────────────────────────────────────────────
    audits = []
    for inc in incidents:
        audits.append({"timestamp": inc["timestamp"], "action": "INCIDENT_RECEIVED_AUTO", "incident_id": inc["id"], "drone_id": "N/A", "reason": "System stress test trace."})
        if inc["assigned_drone"]:
            audits.append({"timestamp": inc["timestamp"] + datetime.timedelta(seconds=5), "action": "AUTO_DISPATCH", "incident_id": inc["id"], "drone_id": inc["assigned_drone"], "reason": "Auto-dispatch test."})

    result2 = await db.audit.insert_many(audits)
    print(f"✅ Inserted {len(result2.inserted_ids)} audit entries")

    client.close()
    print("\n🎉 Seed complete! The frontend will show 3 incidents on next poll.")


if __name__ == "__main__":
    asyncio.run(seed())
