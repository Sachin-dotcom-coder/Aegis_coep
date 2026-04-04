import asyncio
from app.models.incidents_models import Incident
from app.routes.incidents_routes import create_incident
from app.main import lifespan
from app.main import app
import datetime

async def test():
    async with lifespan(app):
        incident = Incident(
            id="INC-NEW-003",
            zone_id="Z1",
            zone_accident_frequency=0.9,
            type="road_accident",
            severity=7.5,
            camera_id="CAM-12",
            camera_coverage=1000,
            people_in_frame=45,
            lat=21.171,
            lng=72.833,
            detect_confidence=0.88,
            timestamp=datetime.datetime.utcnow()
        )
        try:
            res = await create_incident(incident)
            print("SUCCESS:", res)
        except BaseException as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
