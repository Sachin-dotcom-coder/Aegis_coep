import pytest
from unittest.mock import patch, AsyncMock

@pytest.fixture(autouse=True)
def mock_lifespan_tasks():
    with patch("app.db.mongo.connect_mongo", new_callable=AsyncMock) as mock_connect, \
         patch("app.db.mongo.disconnect_mongo", new_callable=AsyncMock) as mock_disconnect, \
         patch("app.main.fleet.run", new_callable=AsyncMock) as mock_fleet_run:
        yield
