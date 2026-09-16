from fastapi import WebSocket

NEW_INCIDENT = 'NEW_INCIDENT'
INCIDENT_ASSIGNED = 'INCIDENT_ASSIGNED'
INCIDENT_UPDATED = 'INCIDENT_UPDATED'
INCIDENT_REASSIGNED = 'INCIDENT_REASSIGNED'
SHIFT_CHANGED = 'SHIFT_CHANGED'
EMPLOYEE_STATUS_CHANGED = 'EMPLOYEE_STATUS_CHANGED'
NOTIFICATION_CREATED = 'NOTIFICATION_CREATED'

class WebSocketManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        
    async def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            
    async def send_to_user(self, user_id: str, event: str, data: dict):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                await connection.send_json({"event": event, "data": data})
                
    async def broadcast_to_admins(self, event: str, data: dict):
        pass
        
    async def broadcast_all(self, event: str, data: dict):
        for connections in self.active_connections.values():
            for connection in connections:
                try:
                    await connection.send_json({"event": event, "data": data})
                except Exception:
                    pass

ws_manager = WebSocketManager()
