import asyncio, math, json
from enum import Enum
from app.services.priority import calculate_dynamic_priority

# Configuration
BATTERY_DRAIN_RATE = 0.03
BATTERY_CHARGE_RATE = 0.05
DRONE_SPEED_LATLNG = 0.0003

class DroneState(Enum):
    IDLE = "idle"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    RECALLED = "recalled"
    CHARGING = "charging"

# Geofencing: Defined as list of circles (lat, lng, radius_in_latlng)
NO_FLY_ZONES = [
    # Area 1: Pune Airport / Military (Viman Nagar North)
    (18.5850, 73.9200, 0.025),
    # Area 2: Central Protected Zone (Military Camp area)
    (18.5250, 73.8850, 0.020),
    # Area 3: University / Government restricted (Near NW)
    (18.5550, 73.8250, 0.018),
    # Area 4: South Perimeter (SE of D4 Katraj)
    (18.4350, 73.9290, 0.028)
]

def is_in_nfz(lat, lng):
    """Simple distance check for circular NFZs."""
    for zlat, zlng, zrad in NO_FLY_ZONES:
        dist = math.sqrt((lat - zlat)**2 + (lng - zlng)**2)
        if dist < zrad:
            return True
    return False

class Drone:
    def __init__(self, drone_id, start_lat, start_lng, charging_stations):
        self.id = drone_id
        self.lat = start_lat
        self.lng = start_lng
        self.charging_stations = charging_stations
        self.battery = 100.0
        self.state = DroneState.IDLE
        self.mission_dist = 0.0
        self.target = None
        self.assigned_incident = None
        self.assigned_incident_obj = None
        self.dwell_timer = 0
        self.assigned_priority = 0.0

    def dispatch(self, target_lat, target_lng, incident_obj, priority):
        self.mission_dist = math.sqrt((target_lat - self.lat)**2 + (target_lng - self.lng)**2)
        self.target = (target_lat, target_lng)
        self.assigned_incident_obj = incident_obj
        self.assigned_incident = incident_obj.get("id") if incident_obj else None
        self.assigned_priority = priority
        self.state = DroneState.EN_ROUTE
        self.dwell_timer = 0
        return True

    def recall(self, target_station=None):
        if target_station:
            self.mission_dist = math.sqrt((target_station[0] - self.lat)**2 + (target_station[1] - self.lng)**2)
            self.target = target_station
        self.state = DroneState.RECALLED
        return_incident = self.assigned_incident_obj
        self.assigned_incident = None
        self.assigned_incident_obj = None
        self.assigned_priority = 0.0
        return return_incident

    def tick(self):
        events = []
        if self.state in (DroneState.EN_ROUTE, DroneState.RECALLED):
            self._move_toward(self.target)
            self.battery = max(0.0, self.battery - BATTERY_DRAIN_RATE)
            if self._arrived():
                if self.state == DroneState.EN_ROUTE:
                    self.state = DroneState.ON_SCENE
                    self.dwell_timer = 15
                    events.append(("DRONE_ON_SCENE", getattr(self, 'assigned_incident', None)))
                else: 
                    self.state = DroneState.CHARGING
                    events.append(("DRONE_CHARGING", None))
        elif self.state == DroneState.ON_SCENE:
            self.battery = max(0.0, self.battery - BATTERY_DRAIN_RATE)
            self.dwell_timer -= 1
            if self.dwell_timer <= 0:
                events.append(("DRONE_TASK_COMPLETE", getattr(self, 'assigned_incident', None)))
                # Become IDLE, waiting for fleet run loop to trigger return-to-station
                self.state = DroneState.IDLE
                self.assigned_incident = None
                self.assigned_incident_obj = None
                self.assigned_priority = 0.0
        elif self.state == DroneState.CHARGING:
            self.battery = min(100.0, self.battery + BATTERY_CHARGE_RATE)
            if self.battery >= 100.0:
                self.state = DroneState.IDLE
        elif self.state == DroneState.IDLE:
            if self.target is not None:
                self.battery = min(100.0, self.battery + BATTERY_CHARGE_RATE)
        
        return events

    def _move_toward(self, target):
        if not target: return
        dlat = target[0] - self.lat
        dlng = target[1] - self.lng
        dist = math.sqrt(dlat**2 + dlng**2)
        
        move_dist = DRONE_SPEED_LATLNG
        if dist < move_dist:
            self.lat, self.lng = target[0], target[1]
            return

        # Proposed next step
        next_lat = self.lat + (dlat / dist) * move_dist
        next_lng = self.lng + (dlng / dist) * move_dist

        # Collision avoidance: simple tangential slip logic
        if is_in_nfz(next_lat, next_lng):
            # Try sliding: Rotate vector 45/-45 deg to find exit
            for angle in [45, -45, 90, -90, 135, -135]:
                rad = math.radians(angle)
                rot_lat = (dlat * math.cos(rad) - dlng * math.sin(rad))
                rot_lng = (dlat * math.sin(rad) + dlng * math.cos(rad))
                mag = math.sqrt(rot_lat**2 + rot_lng**2)
                
                try_lat = self.lat + (rot_lat / mag) * move_dist
                try_lng = self.lng + (rot_lng / mag) * move_dist
                
                if not is_in_nfz(try_lat, try_lng):
                    self.lat, self.lng = try_lat, try_lng
                    return
            # If completely stuck, stop moving
            return

        self.lat, self.lng = next_lat, next_lng

    def _arrived(self):
        if not self.target: return False
        return math.isclose(self.lat, self.target[0], abs_tol=1e-5) and math.isclose(self.lng, self.target[1], abs_tol=1e-5)

    def to_json(self):
        rem_dist = math.sqrt((self.target[0] - self.lat)**2 + (self.target[1] - self.lng)**2) if self.target else 0.0
        # Initialize mission_dist if it was somehow missed or at 0
        if not hasattr(self, 'mission_dist') or self.mission_dist <= 0:
            self.mission_dist = rem_dist if rem_dist > 0 else 1e-9

        eta = rem_dist / DRONE_SPEED_LATLNG if self.target else 0.0
        progress = 100.0 * (1.0 - (rem_dist / self.mission_dist)) if self.mission_dist > 0 else 0.0
            
        return {
            "drone_id": self.id,
            "state": self.state.value if hasattr(self.state, 'value') else str(self.state),
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "battery": round(self.battery, 1),
            "assigned_incident": self.assigned_incident,
            "eta_seconds": int(eta) if self.state in (DroneState.EN_ROUTE, DroneState.RECALLED) else 0,
            "path_progress": round(min(100.0, max(0.0, progress)), 1),
            "charging_progress": round(self.battery, 1) if self.state == DroneState.CHARGING else 0
        }

class DroneFleet:
    def __init__(self):
        self.stations = [
            (18.6200, 73.8300), # Bhosari Industrial
            (18.5600, 73.9400), # Kharadi HQ
            (18.5900, 73.7400), # Hinjewadi IT
            (18.4600, 73.8500), # Katraj Bypass
            (18.4500, 73.7000)  # Paud Valley (D5 Down Left)
        ]
        
        self.drones = {}
        drone_number = 1
        for station in self.stations:
            for _ in range(3):
                did = f"D{drone_number}"
                self.drones[did] = Drone(did, station[0], station[1], self.stations)
                self.drones[did].target = station
                drone_number += 1
                
        self.pending_queue = [] 
        self.active_mission_ids = set() # Track current incident IDs assigned to drones
    def enqueue_incident(self, incident: dict):
        # Prevent queueing the same incident twice
        if not any(i.get("id") == incident.get("id") for i in self.pending_queue):
            self.pending_queue.append(incident)
            self.sort_pending_queue()
        print(f"📥 Pending Queue now has {len(self.pending_queue)} items.")

    def get_station_occupancy(self, station):
        count = 0
        for d in self.drones.values():
            if d.target == station and d.state in (DroneState.RECALLED, DroneState.CHARGING, DroneState.IDLE):
                count += 1
        return count

    def find_nearest_available_station(self, lat, lng):
        sorted_stations = sorted(self.stations, key=lambda s: (s[0]-lat)**2 + (s[1]-lng)**2)
        for s in sorted_stations:
            if self.get_station_occupancy(s) < 3:
                return s
        return sorted_stations[0]

    def trigger_recall(self, drone):
        target = self.find_nearest_available_station(drone.lat, drone.lng)
        old_inc = drone.recall(target)
        if old_inc and old_inc not in self.pending_queue:
            self.pending_queue.append(old_inc)

    def has_enough_battery(self, drone, dest_lat, dest_lng):
        dist_to_inc = math.sqrt((drone.lat - dest_lat)**2 + (drone.lng - dest_lng)**2)
        station = self.find_nearest_available_station(dest_lat, dest_lng)
        dist_to_station = math.sqrt((dest_lat - station[0])**2 + (dest_lng - station[1])**2)
        
        req_cost = (dist_to_inc / DRONE_SPEED_LATLNG) * BATTERY_DRAIN_RATE
        hover_cost = 15 * BATTERY_DRAIN_RATE
        return_cost = (dist_to_station / DRONE_SPEED_LATLNG) * BATTERY_DRAIN_RATE
        return drone.battery > (req_cost + hover_cost + return_cost)

    def best_drone_for(self, lat, lng):
        candidates = [d for d in self.drones.values() if d.state in (DroneState.IDLE, DroneState.CHARGING) and self.has_enough_battery(d, lat, lng)]
        if not candidates:
            return None
        return min(candidates, key=lambda d: (d.lat - lat)**2 + (d.lng - lng)**2)

    def sort_pending_queue(self):
        def get_priority(incident):
            best_drone = self.best_drone_for(incident['lat'], incident['lng'])
            dist = math.sqrt((best_drone.lat - incident['lat'])**2 + (best_drone.lng - incident['lng'])**2) if best_drone else 1.0
            return calculate_dynamic_priority(incident, dist)
        self.pending_queue.sort(key=get_priority, reverse=True)

    async def run(self, broadcast_fn, audit_fn=None):
        print("🚀 Drone Fleet Background Task Started")
        last_db_sync = 0
        last_heartbeat = 0
        while True:
            try:
                loop_time = asyncio.get_event_loop().time()
                
                # ── Heartbeat Log (Every 10s) ─────────
                if loop_time - last_heartbeat > 10.0:
                    active = len(self.active_mission_ids)
                    pending = len(self.pending_queue)
                    print(f"📡 FLEET PULSE: {active} Missions Active | {pending} Pending | All Drones Online")
                    last_heartbeat = loop_time

                # ── Sync with DB periodically (supports manual seeds/ML scripts) 
                if loop_time - last_db_sync > 5.0:
                    from app.db.mongo import get_db
                    db = await get_db()
                    if db is not None:
                        # Find potential incidents not currently in memory or processed
                        cursor = db.incidents.find({
                            "status": {"$in": ["queued", "pending", "auto"]},
                            "assigned_drone": None
                        })
                        async for doc in cursor:
                            inc_id = doc.get("id")
                            in_queue = any(q.get("id") == inc_id for q in self.pending_queue)
                            is_active = inc_id in self.active_mission_ids
                            
                            if inc_id and not in_queue and not is_active:
                                doc.pop("_id", None)
                                self.pending_queue.append(doc)
                    last_db_sync = loop_time

                for drone in self.drones.values():
                    # Tactical standby: Keep drones in the field if incidents are pending.
                    # Only return if battery is critical (< 25%) or if the entire queue is empty.
                    low_battery = drone.battery < 25.0
                    no_pending_tasks = len(self.pending_queue) == 0
                    
                    if drone.state == DroneState.IDLE and drone.assigned_incident is None and not self._is_at_station(drone):
                        if low_battery or no_pending_tasks:
                            self.trigger_recall(drone)
                        
                    events = drone.tick()
                    if events:
                        for event_name, inc_id in events:
                            if event_name == "DRONE_TASK_COMPLETE":
                                if inc_id in self.active_mission_ids:
                                    self.active_mission_ids.remove(inc_id)
                            if audit_fn:
                                asyncio.create_task(audit_fn(event_name, inc_id, drone.id))
                
                self.process_queue(audit_fn)
                
                payload = [d.to_json() for d in self.drones.values()]
                await broadcast_fn(json.dumps(payload))
            except Exception as e:
                import traceback
                print(f"❌ Fleet Tick Error: {e}")
                traceback.print_exc()
            await asyncio.sleep(1)

    def _is_at_station(self, drone):
        if not drone.target: return False
        return drone.target in self.stations and drone._arrived()

    def process_queue(self, audit_fn=None):
        if not self.pending_queue:
            return
            
        self.sort_pending_queue()
        
        for incident in list(self.pending_queue):
            inc_priority = incident.get('priority_score', 0)
            assigned = False
            
            # Check Preemption first
            preempt_candidates = [d for d in self.drones.values() 
                                  if d.state == DroneState.EN_ROUTE 
                                  and inc_priority >= d.assigned_priority + 3
                                  and self.has_enough_battery(d, incident['lat'], incident['lng'])]
                                  
            if preempt_candidates:
                target_drone = min(preempt_candidates, key=lambda d: math.sqrt((d.lat - incident['lat'])**2 + (d.lng - incident['lng'])**2))
                old_inc = target_drone.recall(target_station=self.find_nearest_available_station(target_drone.lat, target_drone.lng))
                if old_inc:
                    self.pending_queue.append(old_inc)
                
                inc_id = incident.get('id', 'N/A')
                print(f"🚀 MISSION START: Drone {target_drone.id} PREEMPTED to {inc_id}")
                target_drone.dispatch(incident['lat'], incident['lng'], incident, inc_priority)
                self.active_mission_ids.add(inc_id) # Lock the mission
                self.pending_queue.remove(incident)
                self.sort_pending_queue()
                
                # Write ETA back
                dist = math.sqrt((target_drone.lat - incident['lat'])**2 + (target_drone.lng - incident['lng'])**2)
                eta = dist / DRONE_SPEED_LATLNG
                incident["eta_seconds"] = int(eta)
                
                if audit_fn:
                    asyncio.create_task(audit_fn("PREEMPTIVE_DISPATCH", inc_id, target_drone.id))
                
                # Sync status to DB
                async def sync_db():
                    from app.db.mongo import get_db
                    db = await get_db()
                    if db is not None:
                        await db.incidents.update_one(
                            {"id": inc_id}, 
                            {"$set": {"status": "en_route", "assigned_drone": target_drone.id, "eta_seconds": int(eta)}}
                        )
                asyncio.create_task(sync_db())
                assigned = True
            
            # If no preemption, try traditional best drone
            if not assigned:
                best_drone = self.best_drone_for(incident['lat'], incident['lng'])
                if best_drone:
                    inc_id = incident.get('id', 'N/A')
                    print(f"🚀 MISSION START: Drone {best_drone.id} dispatched to {inc_id}")
                    best_drone.dispatch(incident['lat'], incident['lng'], incident, inc_priority)
                    self.active_mission_ids.add(inc_id) # Lock the mission
                    self.pending_queue.remove(incident)
                    
                    dist = math.sqrt((best_drone.lat - incident['lat'])**2 + (best_drone.lng - incident['lng'])**2)
                    eta = dist / DRONE_SPEED_LATLNG
                    incident["eta_seconds"] = int(eta)
                    
                    if audit_fn:
                        asyncio.create_task(audit_fn("AUTO_DISPATCH", inc_id, best_drone.id))

                    # Sync status to DB
                    async def sync_db_regular():
                        from app.db.mongo import get_db
                        db = await get_db()
                        if db is not None:
                            await db.incidents.update_one(
                                {"id": inc_id}, 
                                {"$set": {"status": "en_route", "assigned_drone": best_drone.id, "eta_seconds": int(eta)}}
                            )
                    asyncio.create_task(sync_db_regular())
                    assigned = True