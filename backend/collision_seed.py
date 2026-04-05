import asyncio
import datetime
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB_NAME", "Aegis_AI")

async def seed_collision():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB]
    
    print("🗑  Clearing existing incidents...")
    await db.incidents.delete_many({})
    await db.audit.delete_many({})

    now = datetime.datetime.utcnow()
    
    # Perfect head-on collision course
    # Station 1 (North): (18.6200, 73.8300)
    # Station 4 (South): (18.4600, 73.8500)
    # Midpoint Lat: 18.5400
    
    incidents = [
        {
            "id": "COLLISION-NORTH-TARGET",
            "type": "road_accident",
            "severity": 10,
            "lat": 18.5000, # Drone from Station 1 will head SOUTH to this point
            "lng": 73.8400,
            "detect_confidence": 0.9,
            "decision_confidence": 0.9,
            "status": "auto",
            "priority_score": 10.0,
            "timestamp": now,
            "assigned_drone": None,
            "zone_id": "Z1",
            "camera_id": "CAM-TEST-A",
            "zone_accident_frequency": 0.5
        },
        {
            "id": "COLLISION-SOUTH-TARGET",
            "type": "fire",
            "severity": 10,
            "lat": 18.5800, # Drone from Station 4 will head NORTH to this point
            "lng": 73.8400,
            "detect_confidence": 0.9,
            "decision_confidence": 0.9,
            "status": "auto",
            "priority_score": 10.0,
            "timestamp": now,
            "assigned_drone": None,
            "zone_id": "Z1",
            "camera_id": "CAM-TEST-B",
            "zone_accident_frequency": 0.5
        }
    ]

    await db.incidents.insert_many(incidents)
    print("🚀 Collision Test Seed Injected! Two high-priority incidents created in proximity.")
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_collision())
