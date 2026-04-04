import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

async def check_db():
    load_dotenv()
    url = os.getenv("MONGO_URL")
    client = AsyncIOMotorClient(url)
    
    # List all database names
    dbs = await client.list_database_names()
    print(f"Databases found: {dbs}")
    
    # Check collections in aegisai specifically
    if "aegisai" in dbs:
        db = client["aegisai"]
        collections = await db.list_collection_names()
        print(f"Collections in 'aegisai': {collections}")
        
        count = await db.incidents.count_documents({})
        print(f"Total incidents found: {count}")
    else:
        print("ALERT: 'aegisai' database not found on this connection!")

if __name__ == "__main__":
    asyncio.run(check_db())
