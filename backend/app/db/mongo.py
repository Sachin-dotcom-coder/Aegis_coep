from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv(override=True)

_client = None
_db = None

async def connect_mongo():
    global _client, _db
    _client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    _db = _client[os.getenv("MONGO_DB_NAME", "Aegis_AI")]
    print(f"MongoDB Atlas connected to DB: {os.getenv('MONGO_DB_NAME')} ✅")

async def disconnect_mongo():
    _client.close()

async def get_db():
    return _db
...
