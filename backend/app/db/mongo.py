from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

_client = None
_db = None

async def connect_mongo():
    global _client, _db
    _client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    _db = _client["aegisai"]
    print("MongoDB Atlas connected ✅")

async def disconnect_mongo():
    _client.close()

async def get_db():
    return _db
...
