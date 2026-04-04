from fastapi import APIRouter
from pydantic import BaseModel
import datetime

router = APIRouter(prefix="/drones", tags=["drones"])

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
    
    if drone_id not in fleet.drones:
        return {"error": "Drone not found"}
        
    drone = fleet.drones[drone_id]
    # Dispatch manually with highest possible priority so it doesn't get preempted easily
    drone.dispatch(payload.lat, payload.lng, None, 999.0) 
    
    db = await get_db()
    if db is not None:
        await db.audit.insert_one({
            "timestamp": datetime.datetime.utcnow(),
            "action": "ADMIN_DEPLOY_DRONE",
            "drone_id": drone_id,
            "reason": f"Admin dispatched drone to {payload.lat}, {payload.lng} manually."
        })
        
    return {"status": "deployed", "drone_id": drone_id}
