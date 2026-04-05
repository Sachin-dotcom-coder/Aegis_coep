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

async def trigger_collision_test():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[MONGO_DB]
    
    # 1. Clear OLD data
    await db.incidents.delete_many({})
    
    now = datetime.datetime.utcnow()
    
    # Drone A starts North -> Destination South
    # Drone B starts South -> Destination North
    # Each destination is exactly on the opposite side to maximize crossing path
    
    test_incidents = [
        {
            "id": "SYNC-TEST-A",
            "type": "fire", "severity": 9,
            "lat": 18.4410, "lng": 73.8560, 
            "detect_confidence": 0.95, "timestamp": now,
            "decision_confidence": 0.90, "priority_score": 10.0,
            "status": "auto", "assigned_drone": None,
            "zone_id": "TEST", "zone_accident_frequency": 1.0, 
            "camera_id": "TEST-01", "camera_coverage": 100, "people_in_frame": 0
        },
        {
            "id": "SYNC-TEST-B",
            "type": "intrusion", "severity": 9,
            "lat": 18.6200, "lng": 73.8250, 
            "detect_confidence": 0.95, "timestamp": now,
            "decision_confidence": 0.90, "priority_score": 10.0,
            "status": "auto", "assigned_drone": None,
             "zone_id": "TEST", "zone_accident_frequency": 1.0, 
             "camera_id": "TEST-02", "camera_coverage": 100, "people_in_frame": 0
        }
    ]
    
    await db.incidents.insert_many(test_incidents)
    print("\n🚀 CROSSING PATHS: Collision Test Seeded!")
    print("--------------------------------------------------")
    print("Drone from Unit 01 (North) -> Flying South")
    print("Drone from Unit 04 (South) -> Flying North")
    print("They will cross near the city center (18.53, 73.84)")
    print("--------------------------------------------------")
    client.close()

if __name__ == "__main__":
    asyncio.run(trigger_collision_test())
