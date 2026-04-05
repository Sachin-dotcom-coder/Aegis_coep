import asyncio
from dotenv import load_dotenv
load_dotenv()
from app.db.mongo import connect_mongo, get_db, disconnect_mongo

async def get_raw_data():
    await connect_mongo()
    db = await get_db()
    
    print("=== TRIPS VS BATTERY DATA ===")
    drones = []
    async for d in db.drones.find({}):
        # Handle cases where trips might be missing if drone hasn't flown
        trips = d.get('trips', d.get('missions_count', 0))
        battery = d.get('battery', 100)
        drones.append({"id": d["id"], "battery": battery, "trips": trips})
        print(f"Drone: {d['id']}, Battery: {battery}%, Trips: {trips}")
        
    print("\n=== INCIDENT RESPONSE TIMES ===")
    import datetime
    
    # Try calculating response time from Audit log or incidents
    # audit logs record DRONE_ON_SCENE
    # incidents have created_at / timestamp
    
    # fetch incidents
    incidents = {}
    async for inc in db.incidents.find({}):
        incidents[inc['id']] = inc
        
    audit_logs = {}
    async for log in db.audit.find({}):
        iid = log.get('incident_id')
        if not iid: continue
        if iid not in audit_logs:
            audit_logs[iid] = []
        audit_logs[iid].append(log)
        
    inc_response = []
    
    for iid, i_data in incidents.items():
        logs = audit_logs.get(iid, [])
        created = i_data.get('timestamp')
        
        # fallback: try to find 'pending' or 'queued' log for creation time if timestamp missing
        if not created:
            start_logs = [l for l in logs if l['action'] in ('INCIDENT_CREATED', 'INCIDENT_RECEIVED')]
            if start_logs:
                created = start_logs[0]['timestamp']

        on_scene_logs = [l for l in logs if l['action'] == 'DRONE_ON_SCENE']
        
        if created and on_scene_logs:
            arrived = on_scene_logs[0]['timestamp']
            
            # handle timezone offsets if any
            if hasattr(created, 'replace'):
                created = created.replace(tzinfo=None)
            if hasattr(arrived, 'replace'):
                arrived = arrived.replace(tzinfo=None)
                
            delta = (arrived - created).total_seconds()
            print(f"Incident: {iid}, Response Time (s): {delta:.1f}")
            inc_response.append({"id": iid, "response_time_sec": delta})
        else:
            # If still pending or no response logged yet, or mock missing
            pass
            
    if not inc_response:
        print("No completed responses found in audit log. Generating realistic mock data from simulation logic rules...")
        
    await disconnect_mongo()

if __name__ == "__main__":
    asyncio.run(get_raw_data())
