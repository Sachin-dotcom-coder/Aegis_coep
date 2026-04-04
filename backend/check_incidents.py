import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

async def check_incidents():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client[os.getenv("MONGO_DB_NAME", "Aegis_AI")]
    print("--- Latest 5 Incidents ---")
    async for doc in db.incidents.find().sort("timestamp", -1).limit(5):
        print(f"{doc['id']} | {doc['type']} | {doc['status']} | {doc['timestamp']} | {doc['lat']}, {doc['lng']}")
    client.close()

if __name__ == "__main__":
    asyncio.run(check_incidents())
