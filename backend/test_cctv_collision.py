import asyncio
import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB_NAME", "Aegis_AI")

async def trigger_cctv_collision():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB]
    
    # 1. Clear old data
    await db.incidents.delete_many({})
    
    now = datetime.datetime.utcnow()
    
    test_incidents = [
        {
            "id": "COLLISION-Z1",
            "type": "fire", "severity": 9,
            # Destination is the Center (Z1)
            "lat": 18.5300, "lng": 73.8500,
            "detect_confidence": 0.95, "timestamp": now,
            "decision_confidence": 0.90, "priority_score": 10.0,
            "status": "auto", "assigned_drone": None,
            "zone_id": "Z1", "zone_accident_frequency": 1.0, "camera_id": "CAM-Z1", "camera_coverage": 100, "people_in_frame": 0
        },
        {
            "id": "COLLISION-Z4",
            "type": "intrusion", "severity": 9,
            # Destination is the South (Z4)
            "lat": 18.4500, "lng": 73.8600,
            "detect_confidence": 0.95, "timestamp": now,
            "decision_confidence": 0.90, "priority_score": 10.0,
            "status": "auto", "assigned_drone": None,
             "zone_id": "Z4", "zone_accident_frequency": 1.0, "camera_id": "CAM-Z4", "camera_coverage": 100, "people_in_frame": 0
        }
    ]
    
    await db.incidents.insert_many(test_incidents)
    print("\n🚀 CCTV COLLISION: Collision Test Seeded at Z1 and Z4!")
    print("--------------------------------------------------")
    print("Watching for crossover between North-originating and South-destination drones.")
    client.close()

if __name__ == "__main__":
    asyncio.run(trigger_cctv_collision())
