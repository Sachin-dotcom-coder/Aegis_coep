import asyncio, math, json
from enum import Enum
from app.services.priority import calculate_dynamic_priority

class DroneState(Enum):
    IDLE = "idle"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    RECALLED = "recalled"
    CHARGING = "charging"

class Drone:
    def __init__(self, drone_id, start_lat, start_lng, charging_stations):
        self.id = drone_id
        self.lat = start_lat
        self.lng = start_lng
        self.charging_stations = charging_stations  # List of (lat, lng) tuples
        self.battery = 100.0
        self.state = DroneState.IDLE
        self.target = None
        self.assigned_incident = None
        self.dwell_timer = 0  # time spent on scene

    def dispatch(self, target_lat, target_lng, incident_id):
        if self.battery < 20:   # safety gate
            return False
        self.target = (target_lat, target_lng)
        self.assigned_incident = incident_id
        self.state = DroneState.EN_ROUTE
        self.dwell_timer = 0
        return True

    def recall(self):
        # Find the absolute closest charging station to current location
        closest_station = min(self.charging_stations, key=lambda s: 
                              (s[0] - self.lat)**2 + (s[1] - self.lng)**2)
        self.target = closest_station
        self.state = DroneState.RECALLED
        self.assigned_incident = None

    def tick(self):  # call every second
        events = []
        if self.state in (DroneState.EN_ROUTE, DroneState.RECALLED):
            self._move_toward(self.target)
            self.battery = max(0.0, self.battery - 0.3)
            if self._arrived():
                if self.state == DroneState.EN_ROUTE:
                    self.state = DroneState.ON_SCENE
                    self.dwell_timer = 15  # wait for 15 seconds
                    events.append(("DRONE_ON_SCENE", getattr(self, 'assigned_incident', None)))
                else: # arrived at base
                    self.state = DroneState.CHARGING
                    self.target = None
                    events.append(("DRONE_CHARGING", None))
        elif self.state == DroneState.ON_SCENE:
            self.battery = max(0.0, self.battery - 0.3)  # hovering drains battery
            self.dwell_timer -= 1
            if self.dwell_timer <= 0:
                events.append(("DRONE_TASK_COMPLETE", getattr(self, 'assigned_incident', None)))
                self.recall()
        elif self.state == DroneState.CHARGING:
            self.battery = min(100.0, self.battery + 0.5)
            if self.battery >= 20:
                self.state = DroneState.IDLE
        elif self.state == DroneState.IDLE:
            self.battery = min(100.0, self.battery + 0.5)
        
        if self.battery < 15 and self.state == DroneState.EN_ROUTE:
            events.append(("LOW_BATTERY_FAILSAFE", getattr(self, 'assigned_incident', None)))
            self.recall()

        return events

    def _move_toward(self, target):
        speed = 0.0003  # degrees per second, ~30m/s
        dlat = target[0] - self.lat
        dlng = target[1] - self.lng
        dist = math.sqrt(dlat**2 + dlng**2)
        if dist > speed:
            self.lat += (dlat / dist) * speed
            self.lng += (dlng / dist) * speed
        else:
            self.lat = target[0]
            self.lng = target[1]

    def _arrived(self):
        if not self.target: return False
        return math.isclose(self.lat, self.target[0], abs_tol=1e-5) and math.isclose(self.lng, self.target[1], abs_tol=1e-5)

    def to_json(self):
        return {
            "drone_id": self.id,
            "state": self.state.value,
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "battery": round(self.battery, 1),
            "assigned_incident": self.assigned_incident,
        }

class DroneFleet:
    def __init__(self):
        # 5 Dispatch Units in Pune, Maharashtra
        self.stations = [
            (18.5300, 73.8500), # Station A (Shivajinagar - Central)
            (18.5500, 73.9300), # Station B (Kharadi - East)
            (18.5900, 73.7300), # Station C (Hinjewadi - West)
            (18.4500, 73.8600), # Station D (Katraj - South)
            (18.5600, 73.9100)  # Station E (Viman Nagar - North)
        ]
        
        self.drones = {}
        drone_number = 1
        # Build 3 drones per unit -> 15 Max Capacity
        for station in self.stations:
            for _ in range(3):
                did = f"D{drone_number}"
                self.drones[did] = Drone(did, station[0], station[1], self.stations)
                drone_number += 1
                
        self.pending_queue = []  # Priority queue of incidents

    def enqueue_incident(self, incident: dict):
        """Add an incident to the queue to be processed by the fleet loop."""
        self.pending_queue.append(incident)
        print(f"📥 Pending Queue now has {len(self.pending_queue)} items.")

    def best_drone_for(self, lat, lng):
        """Pick closest idle drone with enough battery."""
        candidates = [d for d in self.drones.values() 
                      if d.state == DroneState.IDLE and d.battery > 20]
        if not candidates:
            return None
        return min(candidates, key=lambda d: 
                   (d.lat - lat)**2 + (d.lng - lng)**2)

    async def run(self, broadcast_fn, audit_fn=None):
        """Main loop — tick every drone, process queue, broadcast state."""
        print("🚀 Drone Fleet Background Task Started (15 Drones active)!")
        while True:
            try:
                for drone in self.drones.values():
                    events = drone.tick()
                    if audit_fn and events:
                        for event_name, incident_id in events:
                            # Fire and forget audit
                            asyncio.create_task(audit_fn(event_name, incident_id, drone.id))
                
                self.process_queue(audit_fn)
                
                payload = [d.to_json() for d in self.drones.values()]
                await broadcast_fn(json.dumps(payload))
            except Exception as e:
                import traceback
                print(f"❌ Fleet Tick Error: {e}")
                traceback.print_exc()
            await asyncio.sleep(1)

    def process_queue(self, audit_fn=None):
        """Assign drones to queued incidents using dynamic priority."""
        if not self.pending_queue:
            return

        idle_drones = [d for d in self.drones.values() if d.state == DroneState.IDLE and d.battery > 20]
        if not idle_drones:
            return
            
        def get_priority(incident):
            best_drone = self.best_drone_for(incident['lat'], incident['lng'])
            dist = 0.0
            if best_drone:
                dist = math.sqrt((best_drone.lat - incident['lat'])**2 + (best_drone.lng - incident['lng'])**2)
            else:
                dist = 1.0 # arbitrary large penalty
            return calculate_dynamic_priority(incident, dist)

        self.pending_queue.sort(key=get_priority, reverse=True)

        for incident in list(self.pending_queue):
            best_drone = self.best_drone_for(incident['lat'], incident['lng'])
            if best_drone:
                incident_id = incident.get('id', 'N/A')
                print(f"🚀 Dispatching {best_drone.id} to {incident_id}!")
                best_drone.dispatch(incident['lat'], incident['lng'], incident_id)
                self.pending_queue.remove(incident)
                
                if audit_fn:
                    asyncio.create_task(audit_fn("AUTO_DISPATCH", incident_id, best_drone.id))
            else:
                print("⚠️ No drone available for incident!")
                break