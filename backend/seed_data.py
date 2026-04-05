#!/usr/bin/env python3
"""
seed_data.py  —  Aegis AI sample data seeder
Populates MongoDB with realistic incidents and audit entries so the
frontend looks filled from the first load.

Usage (from the backend/ directory):
    python seed_data.py [random_count]
"""

import asyncio
import datetime
import random
import math
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB_NAME", "Aegis_AI")

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


async def seed(random_count: int = 20):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB]

    print("🗑  Clearing existing sample data...")
    await db.incidents.delete_many({"id": {"$regex": "^(INC-|SAFE-|SEED-)"}})
    await db.audit.delete_many({"reason": {"$regex": "System"}})

    now = datetime.datetime.utcnow()

    # ── 3 specific showcase incidents (2 road accidents, 1 fire) ─────────────────
    pinned = [
        {
            "id": "SEED-ACCIDENT-1",
            "zone_id": "Z1", "type": "road_accident", "severity": 9,
            "camera_id": "CAM-SHV-01", "camera_coverage": 400, "people_in_frame": 12,
            "lat": 18.5300, "lng": 73.8500,
            "detect_confidence": 0.88, "timestamp": now - datetime.timedelta(seconds=2),
            "decision_confidence": 0.45, "priority_score": 8.5,
            "status": "pending", "assigned_drone": None, "eta_seconds": None,
            "zone_accident_frequency": 0.8,
        },
        {
            "id": "SEED-ACCIDENT-2",
            "zone_id": "Z4", "type": "road_accident", "severity": 7,
            "camera_id": "CAM-SWG-03", "camera_coverage": 300, "people_in_frame": 8,
            "lat": 18.4500, "lng": 73.8600,
            "detect_confidence": 0.72, "timestamp": now - datetime.timedelta(seconds=5),
            "decision_confidence": 0.40, "priority_score": 6.8,
            "status": "pending", "assigned_drone": None, "eta_seconds": None,
            "zone_accident_frequency": 0.9,
        },
        {
            "id": "SEED-FIRE-1",
            "zone_id": "Z2", "type": "fire", "severity": 10,
            "camera_id": "CAM-VIM-05", "camera_coverage": 500, "people_in_frame": 3,
            "lat": 18.5500, "lng": 73.9300,
            "detect_confidence": 0.95, "timestamp": now - datetime.timedelta(seconds=8),
            "decision_confidence": 0.48, "priority_score": 9.8,
            "status": "pending", "assigned_drone": None, "eta_seconds": None,
            "zone_accident_frequency": 0.6,
        },
    ]

    # ── randomised stress-test incidents ──────────────────────────────────
    random_incidents = []
    for i in range(1, random_count + 1):
        zone     = random.choice(ZONES)
        inc_type = random.choice(INCIDENT_TYPES)

        tier_roll = random.random()
        if tier_roll < 0.25:
            detect = round(random.uniform(0.25, 0.49), 2)
        elif tier_roll < 0.60:
            detect = round(random.uniform(0.50, 0.69), 2)
        else:
            detect = round(random.uniform(0.70, 0.99), 2)

        zone_freq = round(zone["freq"] + random.uniform(-0.1, 0.1), 2)
        decision  = round(detect * zone_freq, 2)
        priority  = round(inc_type["severity"] * decision * random.uniform(0.8, 1.2), 3)

        if detect >= 0.50:
            status = random.choice(["auto", "auto", "pending", "queued"])
        elif decision >= 0.20:
            status = "pending"
        else:
            status = "silent"

        ts = now - datetime.timedelta(minutes=random.randint(0, 120))

        # ── Ensure incident is outside ALL No-Fly Zones ───────────────────────
        def is_in_nfz(lat, lng):
            # Matches backend drone_fleet.py definitions
            nfzs = [
                (18.5850, 73.9200, 0.025), # Pune Airport
                (18.5250, 73.8850, 0.020), # Camp Area
                (18.5550, 73.8250, 0.018), # Govt Restricted
                (18.4350, 73.9290, 0.028)  # South Perimeter
            ]
            for zlat, zlng, zrad in nfzs:
                if math.sqrt((lat - zlat)**2 + (lng - zlng)**2) < zrad:
                    return True
            return False

        trial_lat, trial_lng = 0.0, 0.0
        while True:
            trial_lat = round(zone["lat"] + random.uniform(-0.02, 0.02), 6)
            trial_lng = round(zone["lng"] + random.uniform(-0.02, 0.02), 6)
            if not is_in_nfz(trial_lat, trial_lng):
                break
        # ────────────────────────────────────────────────────────────────────

        random_incidents.append({
            "id":                      f"SEED-{str(i).zfill(3)}",
            "zone_id":                 zone["id"],
            "zone_accident_frequency": zone_freq,
            "type":                    inc_type["type"],
            "severity":                inc_type["severity"],
            "camera_id":               f"{zone['cam']}-{random.randint(1, 9):02d}",
            "camera_coverage":         random.randint(80, 500),
            "people_in_frame":         random.randint(1, 40),
            "lat":                     trial_lat,
            "lng":                     trial_lng,
            "detect_confidence":       detect,
            "timestamp":               ts,
            "decision_confidence":     decision,
            "priority_score":          priority,
            "status":                  status,
            "assigned_drone":          None,
            "eta_seconds":             None,
        })

    all_incidents = pinned + random_incidents
    result = await db.incidents.insert_many(all_incidents)
    print(f"✅ Inserted {len(result.inserted_ids)} incidents  (3 pinned + {random_count} random)")

    silent_count  = sum(1 for i in random_incidents if i["status"] == "silent")
    pending_count = sum(1 for i in random_incidents if i["status"] in ("pending", "queued"))
    auto_count    = sum(1 for i in random_incidents if i["status"] == "auto")
    print(f"   🔴 Silent:         {silent_count}")
    print(f"   🟡 Pending/Queued: {pending_count}")
    print(f"   🟢 Auto-dispatch:  {auto_count}")

    # ── Matching audit trail ──────────────────────────────────────────────────
    actions = [
        "INCIDENT_RECEIVED_AUTO", "INCIDENT_RECEIVED_HUMAN", "AUTO_DISPATCH",
        "HUMAN_OPERATOR_APPROVE", "DRONE_ON_SCENE", "DRONE_TASK_COMPLETE",
    ]
    drone_ids = [f"D{i}" for i in range(1, 16)]
    audits = []
    for inc in all_incidents:
        for _ in range(random.randint(1, 3)):
            audits.append({
                "timestamp":           inc["timestamp"] + datetime.timedelta(seconds=random.randint(0, 120)),
                "action":              random.choice(actions),
                "incident_id":         inc["id"],
                "drone_id":            random.choice(drone_ids),
                "reason":              "System stress test trace.",
                "priority_score":      inc["priority_score"],
                "decision_confidence": inc["decision_confidence"],
            })

    audits.sort(key=lambda e: e["timestamp"], reverse=True)
    result2 = await db.audit.insert_many(audits)
    print(f"✅ Inserted {len(result2.inserted_ids)} audit entries")

    client.close()
    print("\n🎉 Seed complete! Frontend will update on the next 5-second poll.")


if __name__ == "__main__":
    random_count = 20
    if len(sys.argv) > 1:
        try:
            random_count = int(sys.argv[1])
        except ValueError:
            print(f"⚠️ Invalid count '{sys.argv[1]}', defaulting to 20.")
    
    asyncio.run(seed(random_count))
