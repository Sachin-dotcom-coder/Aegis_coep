import pytest
from app.services.drone_fleet import DroneFleet, DroneState

def test_fleet_initialization():
    fleet = DroneFleet()
    assert len(fleet.stations) == 5
    assert len(fleet.drones) == 15
    assert all(d.state == DroneState.IDLE for d in fleet.drones.values())

def test_best_drone_selection():
    fleet = DroneFleet()
    # Station A is (18.53, 73.85)
    incident_lat, incident_lng = 18.5305, 73.8505
    best_drone = fleet.best_drone_for(incident_lat, incident_lng)
    
    # Should pick one from D1-D3 (Station A drones)
    assert best_drone.id in ["D1", "D2", "D3"]

def test_enqueue_incident():
    fleet = DroneFleet()
    incident = {"id": "INC1", "lat": 18.53, "lng": 73.85, "severity": 5}
    fleet.enqueue_incident(incident)
    assert len(fleet.pending_queue) == 1

def test_process_queue():
    fleet = DroneFleet()
    incident = {"id": "INC1", "lat": 18.53, "lng": 73.85, "severity": 5}
    fleet.enqueue_incident(incident)
    
    # Run process_queue
    fleet.process_queue()
    
    assert len(fleet.pending_queue) == 0
    # One drone should be en_route
    en_route_drones = [d for d in fleet.drones.values() if d.state == DroneState.EN_ROUTE]
    assert len(en_route_drones) == 1
    assert en_route_drones[0].assigned_incident == "INC1"
