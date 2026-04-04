from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.services.drone_fleet import DroneFleet
from app.websocket.manager import broadcast
from app.db.mongo import connect_mongo, disconnect_mongo
from app.routes import incidents_routes
from app.websocket.drone_ws import router as ws_router

# Core fleet instance (shared across app loop and api endpoints)
fleet = DroneFleet()

async def log_audit_action(action: str, incident_id: str, drone_id: str = "N/A"):
    """Callback function given to the simulator so it can log to MongoDB safely."""
    from app.db.mongo import get_db
    import datetime
    
    db = await get_db()
    if db is not None:
        await db.audit.insert_one({
            "timestamp": datetime.datetime.utcnow(),
            "action": action,
            "incident_id": incident_id,
            "drone_id": drone_id,
            "reason": f"System trace: {action} executed by fleet."
        })

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Events
    await connect_mongo()
    app.state.drone_task = asyncio.create_task(fleet.run(broadcast, log_audit_action))
    yield
    # Shutdown Events
    app.state.drone_task.cancel()
    await disconnect_mongo()

app = FastAPI(title="AegisAI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Connect HTTP routers
app.include_router(incidents_routes.router)

# Connect WebSocket router
app.include_router(ws_router)