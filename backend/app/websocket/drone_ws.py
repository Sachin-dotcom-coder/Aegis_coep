from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import connected_clients

router = APIRouter()

@router.websocket("/ws/drones")
async def drone_ws(websocket: WebSocket):
    print("🔌 Client trying to connect to WebSocket...")
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"✅ Client connected. Total clients: {len(connected_clients)}")
    try:
        while True:
            await websocket.receive_text()  # keep alive heartbeat
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"❌ Client disconnected. Total clients: {len(connected_clients)}")