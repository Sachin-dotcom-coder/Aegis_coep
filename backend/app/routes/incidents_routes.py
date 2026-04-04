from fastapi import APIRouter
from app.models.incidents_models import Incident
from app.db.mongo import get_db
from app.services.priority import calculate_priority
from app.services.confidence_gate import gate
from app.services.zone_manager import dedup_or_merge
import datetime

router = APIRouter(prefix="/incidents", tags=["incidents"])

@router.post("/")
async def create_incident(incident: Incident):
    db = await get_db()
    
    # 1. Calculate Decision Confidence & Priority
    incident.decision_confidence = incident.detect_confidence * incident.zone_accident_frequency
    incident.priority_score = calculate_priority(incident)
    
    # 2. Confidence gate — what to do with it
    action = gate(incident.decision_confidence)
    incident.status = "pending" if action == "human" else "queued"
    
    print(f"🚦 Incident Received: Confidence ({incident.decision_confidence}) -> Action ({action})")
    
    # 3. Geo dedup — is this the same event as something within 200m?
    merged = await dedup_or_merge(db, incident)
    if merged:
        return {"status": "merged", "incident_id": merged}
    
    print(f"🚦 Incident Received: Confidence ({incident.decision_confidence}) -> Action ({action})")
    
    # Auto-dispatch integration (if logic passes)
    from app.main import fleet
    if action == "auto":
        print("📨 Sending to Drone Fleet Priority Queue!")
        # make sure to use model_dump() or dict() safely
        fleet.enqueue_incident(incident.dict())
    
    # 4. Save
    await db.incidents.insert_one(incident.dict())
    
    # 5. Audit log
    await db.audit.insert_one({
        "timestamp": datetime.datetime.utcnow(),
        "action": f"INCIDENT_RECEIVED_{action.upper()}",
        "incident_id": incident.id,
        "priority_score": incident.priority_score,
        "decision_confidence": incident.decision_confidence,
    })
    
    return {"status": action, "priority_score": incident.priority_score}

@router.post("/{incident_id}/approve")
async def approve_incident(incident_id: str):
    """Operator overrides medium-reliability queue and dispatches drone immediately."""
    db = await get_db()
    existing = await db.incidents.find_one({"id": incident_id})
    if not existing:
        return {"error": "Incident not found"}
        
    # Flip to auto 
    await db.incidents.update_one({"id": incident_id}, {"$set": {"status": "auto"}})
    
    # Strip MongoDB _id hash before queuing because pydantic/simulator doesn't use it
    existing.pop('_id', None)
    
    from app.main import fleet
    fleet.enqueue_incident(existing)
    
    await db.audit.insert_one({
        "timestamp": datetime.datetime.utcnow(),
        "action": "HUMAN_OPERATOR_APPROVE",
        "incident_id": incident_id,
        "reason": "Operator manually confirmed medium-confidence queue."
    })
    return {"status": "approved", "message": "Drone dispatched!"}

@router.post("/{incident_id}/reject")
async def reject_incident(incident_id: str):
    """Operator explicitly rejects a false positive incident."""
    db = await get_db()
    await db.incidents.update_one({"id": incident_id}, {"$set": {"status": "rejected"}})
    await db.audit.insert_one({
        "timestamp": datetime.datetime.utcnow(),
        "action": "HUMAN_OPERATOR_REJECT",
        "incident_id": incident_id,
        "reason": "Operator discarded as false positive."
    })
    return {"status": "rejected"}

@router.post("/{incident_id}/resolve")
async def resolve_incident(incident_id: str):
    """Admin manually marks an incident as completely resolved."""
    db = await get_db()
    await db.incidents.update_one({"id": incident_id}, {"$set": {"status": "resolved"}})
    
    # Inform audit
    await db.audit.insert_one({
        "timestamp": datetime.datetime.utcnow(),
        "action": "INCIDENT_RESOLVED",
        "incident_id": incident_id,
        "reason": "Admin marked incident as resolved."
    })
    
    return {"status": "resolved"}

@router.post("/{incident_id}/cancel")
async def cancel_incident(incident_id: str):
    """Admin forcibly cancels an incident, removing it from active workflow."""
    db = await get_db()
    await db.incidents.update_one({"id": incident_id}, {"$set": {"status": "cancelled"}})
    
    # Try removing from pending queue if it's there
    from app.main import fleet
    for q_incident in list(fleet.pending_queue):
        if q_incident.get("id") == incident_id:
            fleet.pending_queue.remove(q_incident)
            
    # If a drone is actively flying to it, recall the drone
    for drone in fleet.drones.values():
        if drone.assigned_incident == incident_id:
            drone.recall()
            
    await db.audit.insert_one({
        "timestamp": datetime.datetime.utcnow(),
        "action": "INCIDENT_CANCELLED",
        "incident_id": incident_id,
        "reason": "Admin forcibly cancelled incident."
    })
    return {"status": "cancelled"}

@router.get("/")
async def list_incidents(status: str = None):
    db = await get_db()
    query = {"status": status} if status else {}
    incidents = await db.incidents.find(query).sort("priority_score", -1).to_list(50)
    for i in incidents:
        i["_id"] = str(i["_id"])
    return incidents