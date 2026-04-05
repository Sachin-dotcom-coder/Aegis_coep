import asyncio
import datetime
import math
import random
import sys
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

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

async def seed(random_count: int = 11):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB]
    print("🗑  Clearing existing data...")
    await db.incidents.delete_many({})
    await db.audit.delete_many({})

    all_incidents = []
    now = datetime.datetime.utcnow()
    
    # ── Pinned Clean Starters ──────────────────────────────────────────────
    all_incidents.append({
        "id": "SAFE-AUTO-DISPATCH", "type": "road_accident", "severity": 9,
        "lat": 18.5300, "lng": 73.8500, "detect_confidence": 0.95, "decision_confidence": 0.85,
        "status": "auto", "priority_score": 9.5, "timestamp": now, "assigned_drone": None,
        "zone_id": "Z1", "zone_accident_frequency": 0.8, "camera_id": "CAM-01"
    })

    # ── 3 specific showcase incidents (2 road accidents, 1 fire) ─────────────────
    all_incidents.extend([
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
    ])

    # ── randomised stress-test incidents ──────────────────────────────────
    used_zones = set()
    for i in range(1, random_count + 1):
        # Prefer an unused zone if available to maximize drone spread
        available = [z for z in ZONES if z["id"] not in used_zones]
        zone = random.choice(available if available else ZONES)
        used_zones.add(zone["id"])
        
        inc_type = random.choice(INCIDENT_TYPES)
        detect = round(random.uniform(0.1, 0.99), 2)
        zone_freq = round(zone["freq"] + random.uniform(-0.1, 0.1), 2)
        decision = round(detect * zone_freq, 2)
        
        # ── THE NEW GATE RULES (40% THRESHOLD) ──────────────────────────
        if detect >= 0.40 and decision >= 0.40:
            status = "auto"
        elif detect >= 0.40 or decision >= 0.40:
            status = "pending"
        else:
            status = "silent"
            
        all_incidents.append({
            "id": f"SEED-{i:02d}", "type": inc_type["type"], "severity": inc_type["severity"],
            "lat": zone["lat"], "lng": zone["lng"], "detect_confidence": detect,
            "decision_confidence": decision, "status": status, "priority_score": round(inc_type["severity"] * decision, 2),
            "timestamp": now - datetime.timedelta(seconds=i*10), "assigned_drone": None,
            "zone_id": zone["id"], "zone_accident_frequency": zone_freq, "camera_id": zone["cam"]
        })


    # ── MERGE TEST INCIDENTS ───────────────────────────────────────────────
    main_merge_id = "SEED-MAIN-MERGE"
    merged_id = "SEED-MERGED"
    merge_type = "fire"
    merge_lat = 18.5700
    merge_lng = 73.8000

    # Main incident
    all_incidents.append({
        "id": main_merge_id, "type": merge_type, "severity": 8,
        "lat": merge_lat, "lng": merge_lng, "detect_confidence": 0.7,
        "decision_confidence": 0.7, "status": "auto", "priority_score": 5.6,
        "timestamp": now, "assigned_drone": None,
        "zone_id": "Z3", "zone_accident_frequency": 0.5, "camera_id": "CAM-KAT",
        "merged_into": None
    })
    # Merged incident (very close to main)
    all_incidents.append({
        "id": merged_id, "type": merge_type, "severity": 8,
        "lat": merge_lat + 0.0001, "lng": merge_lng + 0.0001, "detect_confidence": 0.6,
        "decision_confidence": 0.6, "status": "auto", "priority_score": 4.8,
        "timestamp": now, "assigned_drone": None,
        "zone_id": "Z3", "zone_accident_frequency": 0.5, "camera_id": "CAM-KAT",
        "merged_into": main_merge_id
    })

    await db.incidents.insert_many(all_incidents)
    print(f"✅ Seeding Complete: {len(all_incidents)} UNIQUE zone-pinned incidents inserted (including merge test).")
    client.close()

if __name__ == "__main__":
    count = 11
    if len(sys.argv) > 1: count = int(sys.argv[1])
    asyncio.run(seed(count))
