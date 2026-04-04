import asyncio, math, json
from enum import Enum
from app.services.priority import calculate_dynamic_priority

# Configuration
BATTERY_DRAIN_RATE = 0.2
BATTERY_CHARGE_RATE = 0.4
DRONE_SPEED_LATLNG = 0.0015

class DroneState(Enum):
    IDLE = "idle"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    RECALLED = "recalled"
    CHARGING = "charging"

# Geofencing: Defined as list of circles (lat, lng, radius_in_latlng)
NO_FLY_ZONES = [
    (18.5850, 73.9200, 0.025), # Pune Airport
    (18.5250, 73.8850, 0.020), # Camp Area
    (18.5550, 73.8250, 0.018), # Govt Restricted
    (18.4350, 73.9290, 0.028)  # South Perimeter
]

def is_in_nfz(lat, lng):
    for zlat, zlng, zrad in NO_FLY_ZONES:
        dist = math.sqrt((lat - zlat)**2 + (lng - zlng)**2)
        if dist < zrad: return True
    return False

def get_nfz_aware_distance(p1, p2):
    dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
    if dist < 1e-9: return 0.0
    total_expansion = 0.0
    for cx, cy, r in NO_FLY_ZONES:
        # Distance from NFZ center to the line p1->p2
        area = abs((p2[0]-p1[0])*(cy-p1[0]) - (p1[0]-cx)*(p2[1]-p1[1]))
        h = area / dist
        if h < r:
            # Check if NFZ is actually between p1 and p2 using dot product projection
            dot = (cx - p1[0]) * (p2[0] - p1[0]) + (cy - p1[1]) * (p2[1] - p1[1])
            if 0 < dot < dist**2:
                chord = 2 * math.sqrt(r**2 - h**2)
                # Expand path: Replace straight chord with circular arc
                arc = r * 2 * math.asin(chord / (2 * r))
                total_expansion += (arc - chord)
    return dist + total_expansion

class Drone:
    def __init__(self, drone_id, start_lat, start_lng, charging_stations):
        self.id = drone_id
        self.lat = start_lat
        self.lng = start_lng
        self.charging_stations = charging_stations
        self.battery = 100.0
        self.state = DroneState.IDLE
        self.mission_dist = 0.0
        self.target = (start_lat, start_lng)
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

    def tick(self, other_drones=None):
        events = []
        if self.state in (DroneState.EN_ROUTE, DroneState.RECALLED):
            self._move_toward(self.target, other_drones or [])
            self.battery = max(0.0, self.battery - BATTERY_DRAIN_RATE)
            if self._arrived():
                if self.state == DroneState.EN_ROUTE:
                    self.state = DroneState.ON_SCENE
                    self.dwell_timer = 15
                    events.append(("DRONE_ON_SCENE", getattr(self, 'assigned_incident', None)))
                else: 
                    self.state = DroneState.IDLE
                    events.append(("DRONE_ARRIVED_STATION", None))
        elif self.state == DroneState.ON_SCENE:
            self.battery = max(0.0, self.battery - BATTERY_DRAIN_RATE)
            self.dwell_timer -= 1
            if self.dwell_timer <= 0:
                events.append(("DRONE_TASK_COMPLETE", getattr(self, 'assigned_incident', None)))
                self.state = DroneState.IDLE
                self.assigned_incident = None
                self.assigned_incident_obj = None
                self.assigned_priority = 0.0
        elif self.state == DroneState.CHARGING:
            self.battery = min(100.0, self.battery + BATTERY_CHARGE_RATE)
            if self.battery >= 100.0:
                self.state = DroneState.IDLE
        return events

    def _move_toward(self, target, other_drones):
        if not target: return
        dlat = target[0] - self.lat
        dlng = target[1] - self.lng
        dist = math.sqrt(dlat**2 + dlng**2)
        move_dist = DRONE_SPEED_LATLNG
        if dist < move_dist:
            self.lat, self.lng = target[0], target[1]
            return

        next_lat = self.lat + (dlat / dist) * move_dist
        next_lng = self.lng + (dlng / dist) * move_dist

        collision_risk = False
        for od in other_drones:
            if od.id == self.id: continue
            # Maintain 50m (0.0005 deg) exclusion boundary between airborne drones
            if math.sqrt((next_lat - od.lat)**2 + (next_lng - od.lng)**2) < 0.0005:
                collision_risk = True
                break

        if is_in_nfz(next_lat, next_lng) or collision_risk:
            for angle in [45, -45, 90, -90, 135, -135]:
                rad = math.radians(angle)
                rot_lat = (dlat * math.cos(rad) - dlng * math.sin(rad))
                rot_lng = (dlat * math.sin(rad) + dlng * math.cos(rad))
                mag = math.sqrt(rot_lat**2 + rot_lng**2)
                try_lat = self.lat + (rot_lat / mag) * move_dist
                try_lng = self.lng + (rot_lng / mag) * move_dist
                
                if not is_in_nfz(try_lat, try_lng):
                    dodge_collide = False
                    for od in other_drones:
                        if od.id != self.id and math.sqrt((try_lat - od.lat)**2 + (try_lng - od.lng)**2) < 0.0005:
                            dodge_collide = True
                            break
                    if not dodge_collide:
                        self.lat, self.lng = try_lat, try_lng
                        return
            # Blocked: hover in place
            return
            
        self.lat, self.lng = next_lat, next_lng

    def _arrived(self):
        if not self.target: return False
        return math.isclose(self.lat, self.target[0], abs_tol=1e-5) and math.isclose(self.lng, self.target[1], abs_tol=1e-5)

    def to_json(self):
        rem_dist = get_nfz_aware_distance((self.lat, self.lng), (self.target[0], self.target[1])) if self.target else 0.0
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
            (18.6200, 73.8300), (18.5600, 73.9400), (18.5900, 73.7400),
            (18.4600, 73.8500), (18.4500, 73.7000)
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
        self.active_mission_ids = set()

    def enqueue_incident(self, incident: dict):
        if not any(i.get("id") == incident.get("id") for i in self.pending_queue):
            self.pending_queue.append(incident)
            self.sort_pending_queue()

    def get_charging_count(self, station):
        return sum(1 for d in self.drones.values() if d.target == station and d.state == DroneState.CHARGING)

    def find_nearest_station(self, lat, lng):
        return min(self.stations, key=lambda s: (s[0]-lat)**2 + (s[1]-lng)**2)

    def trigger_recall(self, drone):
        target = self.find_nearest_station(drone.lat, drone.lng)
        old_inc = drone.recall(target)
        if old_inc and old_inc not in self.pending_queue:
            self.pending_queue.append(old_inc)

    def has_enough_battery(self, drone, dest_lat, dest_lng):
        dist_to_inc = math.sqrt((drone.lat - dest_lat)**2 + (drone.lng - dest_lng)**2)
        station = self.find_nearest_station(dest_lat, dest_lng)
        dist_to_station = math.sqrt((dest_lat - station[0])**2 + (dest_lng - station[1])**2)
        req_cost = (dist_to_inc / DRONE_SPEED_LATLNG) * BATTERY_DRAIN_RATE
        hover_cost = 15 * BATTERY_DRAIN_RATE
        return_cost = (dist_to_station / DRONE_SPEED_LATLNG) * BATTERY_DRAIN_RATE
        return drone.battery > (req_cost + hover_cost + return_cost)

    def best_drone_for(self, lat, lng):
        candidates = []
        for d in self.drones.values():
            if d.state not in (DroneState.IDLE, DroneState.CHARGING, DroneState.RECALLED, DroneState.EN_ROUTE):
                continue
            if not self.has_enough_battery(d, lat, lng):
                print(f"⚠️ Drone {d.id} disqualified for ({lat}, {lng}): Not enough battery.")
                continue
            candidates.append(d)
            
        if not candidates:
            print(f"⚠️ Fleet WARNING: No drones available to dispatch to ({lat}, {lng})! All disqualified.")
            return None
        def score_drone(d):
            nfz_dist = get_nfz_aware_distance((d.lat, d.lng), (lat, lng))
            dist_sq = nfz_dist**2
            penalty = 0.006 if d.state == DroneState.EN_ROUTE else 0.0
            battery_bias = (100.0 - d.battery) * 0.0001
            return dist_sq + penalty + battery_bias
        return min(candidates, key=score_drone)

    def sort_pending_queue(self):
        def get_priority(incident):
            raw_lat = incident.get('lat')
            raw_lng = incident.get('lng')
            if raw_lat is None: raw_lat = incident.get('latitude')
            if raw_lng is None: raw_lng = incident.get('longitude')
            
            inc_lat = float(raw_lat) if raw_lat is not None else 0.0
            inc_lng = float(raw_lng) if raw_lng is not None else 0.0
            
            best_drone = self.best_drone_for(inc_lat, inc_lng)
            dist = math.sqrt((best_drone.lat - inc_lat)**2 + (best_drone.lng - inc_lng)**2) if best_drone else 1.0
            return calculate_dynamic_priority(incident, dist)
        self.pending_queue.sort(key=get_priority, reverse=True)

    async def run(self, broadcast_fn, audit_fn=None):
        last_db_sync = 0
        last_heartbeat = 0
        while True:
            try:
                loop_time = asyncio.get_event_loop().time()
                if loop_time - last_heartbeat > 10.0:
                    print(f"📡 FLEET PULSE: {len(self.active_mission_ids)} Active | {len(self.pending_queue)} Pending")
                    last_heartbeat = loop_time
                if loop_time - last_db_sync > 5.0:
                    from app.db.mongo import get_db
                    db = await get_db()
                    if db is not None:
                        cursor = db.incidents.find({"status": {"$in": ["queued", "pending", "auto"]}, "assigned_drone": None})
                        async for doc in cursor:
                            if doc.get("id") and not any(q.get("id") == doc["id"] for q in self.pending_queue) and doc["id"] not in self.active_mission_ids:
                                doc.pop("_id", None)
                                self.pending_queue.append(doc)
                    last_db_sync = loop_time
                for drone in self.drones.values():
                    if drone.state == DroneState.IDLE and drone.battery < 100.0 and self._is_at_station(drone):
                        if self.get_charging_count(drone.target) < 3: drone.state = DroneState.CHARGING
                    if drone.state == DroneState.IDLE and drone.assigned_incident is None and not self._is_at_station(drone):
                        print(f"📡 UNIT RECOVERY: Drone {drone.id} returning to base.")
                        self.trigger_recall(drone)
                    events = drone.tick(other_drones=list(self.drones.values()))
                    if events:
                        for event_name, inc_id in events:
                            if event_name == "DRONE_TASK_COMPLETE" and inc_id in self.active_mission_ids:
                                self.active_mission_ids.remove(inc_id)
                            if audit_fn: asyncio.create_task(audit_fn(event_name, inc_id, drone.id))
                self.process_queue(audit_fn)
                await broadcast_fn(json.dumps([d.to_json() for d in self.drones.values()]))
            except Exception as e:
                print(f"❌ Fleet Tick Error: {e}")
            await asyncio.sleep(1)

    def _is_at_station(self, drone):
        return drone.target in self.stations and drone._arrived()

    def process_queue(self, audit_fn=None):
        if not self.pending_queue: return
        self.sort_pending_queue()
        for incident in list(self.pending_queue):
            inc_priority = incident.get('priority_score', 0)
            inc_id = incident.get('id', 'N/A')
            
            # Robust extraction of coordinates (avoids NoneType errors when keys exist but equal None)
            raw_lat = incident.get('lat')
            raw_lng = incident.get('lng')
            if raw_lat is None: raw_lat = incident.get('latitude')
            if raw_lng is None: raw_lng = incident.get('longitude')
            
            inc_lat = float(raw_lat) if raw_lat is not None else 0.0
            inc_lng = float(raw_lng) if raw_lng is not None else 0.0
            
            # Prevent swarm dispatch for concurrently created duplicate incidents
            already_covered = False
            for d in self.drones.values():
                if d.state in (DroneState.EN_ROUTE, DroneState.ON_SCENE) and hasattr(d, 'target') and d.target:
                    coverage_dist = math.sqrt((d.target[0] - inc_lat)**2 + (d.target[1] - inc_lng)**2)
                    if coverage_dist < 0.002:
                        already_covered = True
                        break
            
            if already_covered:
                print(f"🛑 SWARM PREVENTED: Incident {inc_id} covered by active drone. Dropping.")
                self.pending_queue.remove(incident)
                async def mark_merged(i_id=inc_id):
                    from app.db.mongo import get_db
                    db = await get_db()
                    if db is not None:
                        await db.incidents.update_one({"id": i_id}, {"$set": {"status": "merged"}})
                asyncio.create_task(mark_merged())
                continue

            best_drone = self.best_drone_for(inc_lat, inc_lng)
            if best_drone:
                if best_drone.state == DroneState.EN_ROUTE:
                    if inc_priority < best_drone.assigned_priority + 2: continue 
                    print(f"🚀 MISSION HIJACK: Drone {best_drone.id} diverted to {inc_id}")
                elif best_drone.state == DroneState.RECALLED:
                    print(f"🔄 MISSION DIVERT: Homebound {best_drone.id} intercepted for {inc_id}!")
                else:
                    print(f"🚀 MISSION START: Drone {best_drone.id} dispatched to {inc_id}")
                dist = get_nfz_aware_distance((best_drone.lat, best_drone.lng), (inc_lat, inc_lng))
                eta = int(dist / DRONE_SPEED_LATLNG)
                best_drone.dispatch(inc_lat, inc_lng, incident, inc_priority)
                # Ensure the mission_dist is correctly set in dispatch as the awareness dist
                best_drone.mission_dist = dist
                self.active_mission_ids.add(inc_id)
                self.pending_queue.remove(incident)
                if audit_fn: asyncio.create_task(audit_fn("HIJACK_DISPATCH" if best_drone.state == DroneState.EN_ROUTE else "AUTO_DISPATCH", inc_id, best_drone.id))
                async def sync_db():
                    from app.db.mongo import get_db
                    db = await get_db()
                    if db is not None:
                        await db.incidents.update_one({"id": inc_id}, {"$set": {"status": "en_route", "assigned_drone": best_drone.id, "eta_seconds": eta}})
                asyncio.create_task(sync_db())