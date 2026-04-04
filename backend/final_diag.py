import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

async def diag():
    load_dotenv()
    url = os.getenv("MONGO_URL")
    client = AsyncIOMotorClient(url)
    
    # Wait for connection
    await client.admin.command('ping')
    
    # Get all dbs
    dbs = await client.list_database_names()
    print(f"DBS found by code: {dbs}")
    
    # Check collections
    if "AegisAI_Fleet" in dbs:
        print("Success: AegisAI_Fleet database found.")
        db = client["AegisAI_Fleet"]
        print(f"Collections: {await db.list_collection_names()}")
    elif "aegisai" in dbs:
        print("Success: aegisai database found.")
        db = client["aegisai"]
        print(f"Collections: {await db.list_collection_names()}")
    else:
        print("Error: Targeted database NOT found.")

if __name__ == "__main__":
    asyncio.run(diag())
