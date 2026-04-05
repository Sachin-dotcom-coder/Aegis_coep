from fastapi import APIRouter
from pydantic import BaseModel
import datetime

router = APIRouter(prefix="/drones", tags=["drones"])

@router.get("/")
async def list_drones():
    """Return current state of the entire drone fleet."""
    from app.main import fleet
    return [d.to_json() for d in fleet.drones.values()]

@router.get("/stations")
async def list_stations():
    """Return the fixed coordinates of dispatch units."""
    from app.main import fleet
    return [
        {"id": f"STN-0{i+1}", "lat": s[0], "lng": s[1]}
        for i, s in enumerate(fleet.stations)
    ]

class DeployPayload(BaseModel):
    lat: float
    lng: float

@router.post("/{drone_id}/recall")
async def recall_drone(drone_id: str):
    from app.main import fleet
    from app.db.mongo import get_db
    
    if drone_id not in fleet.drones:
        return {"error": "Drone not found"}
        
    drone = fleet.drones[drone_id]
    
    # Check if drone was actively assigned an incident to unassign physically in queue
    old_inc = None
    if drone.assigned_incident:
        old_inc = drone.assigned_incident

    fleet.trigger_recall(drone)
    
    db = await get_db()
    if db is not None:
        await db.audit.insert_one({
            "timestamp": datetime.datetime.utcnow(),
            "action": "ADMIN_RECALL_DRONE",
            "drone_id": drone_id,
            "incident_id": old_inc if old_inc else "N/A",
            "reason": "Admin forcibly recalled drone mid-flight."
        })
        
    return {"status": "recalled", "drone_id": drone_id}

@router.post("/{drone_id}/deploy")
async def deploy_drone(drone_id: str, payload: DeployPayload):
    from app.main import fleet
    from app.db.mongo import get_db
    import uuid
    
    if drone_id not in fleet.drones:
        return {"error": "Drone not found"}
        
    drone = fleet.drones[drone_id]
    
    # Create a manual incident
    manual_inc_id = f"MANUAL-{uuid.uuid4().hex[:6].upper()}"
    incident_obj = {
        "id": manual_inc_id,
        "type": "manual_deployment",
        "lat": payload.lat,
        "lng": payload.lng,
        "status": "dispatched",
        "priority_score": 999.0,
        "detect_confidence": 1.0,
        "zone_accident_frequency": 1.0,
        "severity": 10,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "assigned_drone": drone_id,
        "camera_id": "MANUAL-OP",
        "people_in_frame": 0,
        "zone_id": "MANUAL",
        "decision_confidence": 1.0,
        "priority_score": 999.0
    }
    
    # Dispatch manually with highest possible priority so it doesn't get preempted easily
    drone.dispatch(payload.lat, payload.lng, incident_obj, 999.0) 
    
    db = await get_db()
    if db is not None:
        await db.incidents.insert_one(incident_obj)
        await db.audit.insert_one({
            "timestamp": datetime.datetime.utcnow(),
            "action": "ADMIN_DEPLOY_DRONE",
            "drone_id": drone_id,
            "incident_id": manual_inc_id,
            "reason": f"Admin dispatched drone to {payload.lat}, {payload.lng} manually."
        })
        
    return {"status": "deployed", "drone_id": drone_id, "incident_id": manual_inc_id}

@router.post("/reset")
async def reset_fleet():
    """Wipe all active missions and reset drone positions."""
    from app.main import fleet
    from app.db.mongo import get_db
    
    # 1. Reset in-memory fleet state
    fleet.reset_fleet()
    
    # 2. Clear incidents and audits from DB for a true clean slate
    db = await get_db()
    if db is not None:
        await db.incidents.delete_many({"id": {"$regex": "^(INC-|SAFE-|SEED-|MANUAL-)"}})
        await db.audit.delete_many({"reason": {"$regex": "System|Admin"}})
        
    return {"status": "success", "message": "Fleet and DB reset to clean state."}
