import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
@patch("app.routes.incidents_routes.get_db")
@patch("app.routes.incidents_routes.dedup_or_merge")
@patch("app.main.fleet")
async def test_create_incident(mock_fleet, mock_dedup, mock_get_db, client):
    # Setup mocks
    mock_db = MagicMock()
    mock_db.incidents.insert_one = AsyncMock()
    mock_db.audit.insert_one = AsyncMock()
    mock_get_db.return_value = mock_db
    mock_dedup.return_value = None # No de-duplication
    
    incident_data = {
        "id": "INC123",
        "zone_id": "Z1",
        "zone_accident_frequency": 0.8,
        "type": "fire",
        "severity": 8.0,
        "camera_id": "CAM1",
        "camera_coverage": 100,
        "people_in_frame": 10,
        "lat": 18.5300,
        "lng": 73.8500,
        "detect_confidence": 0.9,
        "timestamp": "2026-04-03T12:00:00Z"
    }
    
    response = await client.post("/incidents/", json=incident_data)
    
    assert response.status_code == 200
    # Verify DB calls
    assert mock_db.incidents.insert_one.called
    assert mock_db.audit.insert_one.called

@pytest.mark.asyncio
@patch("app.routes.incidents_routes.get_db")
async def test_get_incidents(mock_get_db, client):
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    # Mocking Cursor
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[
        {"_id": "some_id", "id": "INC1", "status": "pending"}
    ])
    mock_db.incidents.find.return_value = mock_cursor
    
    response = await client.get("/incidents/")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "INC1"
