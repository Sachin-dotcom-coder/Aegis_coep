# websocket/manager.py
from fastapi import WebSocket
from typing import Set

connected_clients: Set[WebSocket] = set()

async def broadcast(message: str):
    dead = set()
    for ws in connected_clients.copy():
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    # Mutating the set in place prevents UnboundLocalError
    connected_clients.difference_update(dead)