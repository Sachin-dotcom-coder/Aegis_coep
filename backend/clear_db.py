import asyncio
import os
import sys

# adjust import path
sys.path.append(os.path.dirname(__file__))

from app.db.mongo import get_db, connect_mongo, disconnect_mongo

async def clear_db():
    await connect_mongo()
    db = await get_db()
    
    res = await db.incidents.delete_many({})
    print(f"Deleted {res.deleted_count} stale incidents")
    
    await db.audit.delete_many({})
    print("Cleared audit log")
    
    await disconnect_mongo()

if __name__ == "__main__":
    asyncio.run(clear_db())
