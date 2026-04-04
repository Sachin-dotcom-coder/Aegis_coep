import asyncio
import os
from app.db.mongo import connect_mongo, get_db

async def test():
    await connect_mongo()
    db = await get_db()
    print(f"Current database name in app: {db.name}")

if __name__ == "__main__":
    asyncio.run(test())
