from fastapi import APIRouter, Query
from app.db.mongo import get_db
import datetime

router = APIRouter(prefix="/audits", tags=["audits"])

@router.get("/")
async def get_audits(limit: int = Query(100, ge=1, le=500)):
    """Fetch the latest global activity logs from the database."""
    db = await get_db()
    cursor = db.audit.find().sort("timestamp", -1).limit(limit)
    audits = await cursor.to_list(length=limit)
    
    # Ensure MongoDB _id is stringified for JSON serialization
    for a in audits:
        a["_id"] = str(a["_id"])
        if isinstance(a.get("timestamp"), datetime.datetime):
            a["timestamp"] = a["timestamp"].isoformat()
            
    return audits

@router.post("/")
async def add_audit_entry(action: str, incident_id: str = None, drone_id: str = None, reason: str = None):
    """Manually inject an audit entry (used for system events)."""
    db = await get_db()
    entry = {
        "timestamp": datetime.datetime.utcnow(),
        "action": action,
        "incident_id": incident_id,
        "drone_id": drone_id,
        "reason": reason
    }
    await db.audit.insert_one(entry)
    return {"status": "created"}
