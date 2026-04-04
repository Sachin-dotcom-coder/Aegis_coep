import pytest
from app.services.drone_fleet import Drone, DroneState

def test_drone_initialization():
    stations = [(18.5300, 73.8500)]
    drone = Drone("D1", 18.5300, 73.8500, stations)
    assert drone.id == "D1"
    assert drone.state == DroneState.IDLE
    assert drone.battery == 100.0

def test_drone_dispatch():
    stations = [(18.5300, 73.8500)]
    drone = Drone("D1", 18.5300, 73.8500, stations)
    target_lat, target_lng = 18.5400, 73.8600
    
    success = drone.dispatch(target_lat, target_lng, "INC123")
    
    assert success is True
    assert drone.state == DroneState.EN_ROUTE
    assert drone.target == (target_lat, target_lng)
    assert drone.assigned_incident == "INC123"

def test_drone_battery_failsafe():
    stations = [(18.5300, 73.8500)]
    drone = Drone("D1", 18.5300, 73.8500, stations)
    drone.battery = 10.0 # Low battery
    
    success = drone.dispatch(18.5400, 73.8600, "INC123")
    assert success is False
    assert drone.state == DroneState.IDLE

def test_drone_movement_and_arrival():
    stations = [(18.0, 73.0)]
    drone = Drone("D1", 18.0, 73.0, stations)
    # Target is very close to speed (0.0003)
    target = (18.0001, 73.0001)
    drone.dispatch(target[0], target[1], "INC123")
    
    # One tick
    events = drone.tick()
    assert drone.state == DroneState.ON_SCENE
    assert drone.lat == target[0]
    assert drone.lng == target[1]
    assert ("DRONE_ON_SCENE", "INC123") in events

def test_drone_recall_to_closest_station():
    stations = [(18.0, 73.0), (19.0, 74.0)]
    drone = Drone("D1", 18.8, 73.8, stations) # Closer to (19, 74)
    
    drone.recall()
    assert drone.state == DroneState.RECALLED
    assert drone.target == (19.0, 74.0)

def test_drone_charging():
    stations = [(18.0, 73.0)]
    drone = Drone("D1", 18.0, 73.0, stations)
    drone.state = DroneState.CHARGING
    drone.battery = 10.0
    
    drone.tick()
    assert drone.battery == 10.5
    
    drone.battery = 20.0
    drone.tick()
    assert drone.state == DroneState.IDLE
