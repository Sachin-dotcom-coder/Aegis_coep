import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

async def test_conn():
    try:
        url = os.getenv("MONGO_URL")
        print(f"Connecting to: {url}")
        client = AsyncIOMotorClient(url)
        db = client[os.getenv("MONGO_DB_NAME", "Aegis_AI")]
        server_info = await client.server_info()
        print("Connected! server_info:", server_info)
        client.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_conn())
