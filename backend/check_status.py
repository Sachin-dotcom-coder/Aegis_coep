import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

async def check():
    load_dotenv()
    uri = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB_NAME", "Aegis_AI")
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    total = await db.incidents.count_documents({})
    auto = await db.incidents.count_documents({"status": "auto"})
    queued = await db.incidents.count_documents({"status": "queued"})
    pending = await db.incidents.count_documents({"status": "pending"})
    assigned = await db.incidents.count_documents({"assigned_drone": {"$ne": None}})
    
    print(f"TOTAL: {total}")
    print(f"AUTO: {auto}")
    print(f"QUEUED: {queued}")
    print(f"PENDING: {pending}")
    print(f"ASSIGNED: {assigned}")
    
    NFZ = [
        (18.5850, 73.9200, 0.025), # Pune Airport
        (18.5250, 73.8850, 0.020), # Camp Area
        (18.5550, 73.8250, 0.018), # Govt Restricted
        (18.4350, 73.9290, 0.028)  # South Perimeter
    ]
    
    async for d in db.incidents.find():
        lat, lng = d.get('lat', 0), d.get('lng', 0)
        for nz_lat, nz_lng, nz_rad in NFZ:
            dist = math.sqrt((lat-nz_lat)**2 + (lng-nz_lng)**2)
            if dist < nz_rad:
                print(f"🛑 FOUND IN NFZ: Incident {d['id']} at {lat}, {lng} is inside NFZ {nz_lat}, {nz_lng} (dist: {dist:.4f} < {nz_rad})")
                
    client.close()

if __name__ == "__main__":
    asyncio.run(check())
