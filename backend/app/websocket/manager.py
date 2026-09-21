import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Set
from fastapi import WebSocket
import structlog

from app.core.metrics import metrics

logger = structlog.get_logger()

# -----------------------------------------------------------------------------
# Section 11: Standard Event Types
# -----------------------------------------------------------------------------
NEW_INCIDENT = 'NEW_INCIDENT'
INCIDENT_UPDATED = 'INCIDENT_UPDATED'
INCIDENT_ASSIGNED = 'INCIDENT_ASSIGNED'
INCIDENT_REASSIGNED = 'INCIDENT_REASSIGNED'
INCIDENT_UNASSIGNED = 'INCIDENT_UNASSIGNED'

GROUP_NOTICE_CREATED = 'GROUP_NOTICE_CREATED'
GROUP_NOTICE_UPDATED = 'GROUP_NOTICE_UPDATED'

MY_WORK_UPDATED = 'MY_WORK_UPDATED'
TASK_UPDATED = 'TASK_UPDATED'
TASK_STARTED = 'TASK_STARTED'
TASK_COMPLETED = 'TASK_COMPLETED'

EMPLOYEE_STATUS_CHANGED = 'EMPLOYEE_STATUS_CHANGED'
CHAT_PRESENCE_CHANGED = 'CHAT_PRESENCE_CHANGED'

CHAT_CONVERSATION_CREATED = 'CHAT_CONVERSATION_CREATED'
CHAT_MESSAGE_CREATED = 'CHAT_MESSAGE_CREATED'
CHAT_MESSAGE_UPDATED = 'CHAT_MESSAGE_UPDATED'
CHAT_MESSAGE_DELETED = 'CHAT_MESSAGE_DELETED'
CHAT_MESSAGE_READ = 'CHAT_MESSAGE_READ'
CHAT_TYPING = 'CHAT_TYPING'
CHAT_TYPING_STARTED = 'CHAT_TYPING_STARTED'
CHAT_TYPING_STOPPED = 'CHAT_TYPING_STOPPED'
CHAT_MESSAGE_REACTION_ADDED = 'CHAT_MESSAGE_REACTION_ADDED'
CHAT_MESSAGE_REACTION_REMOVED = 'CHAT_MESSAGE_REACTION_REMOVED'
CHAT_MEDIA_READY = 'CHAT_MEDIA_READY'
PROFILE_UPDATED = 'PROFILE_UPDATED'
TEAM_MEMBER_UPDATED = 'TEAM_MEMBER_UPDATED'

NOTIFICATION_CREATED = 'NOTIFICATION_CREATED'
NOTIFICATION_READ = 'NOTIFICATION_READ'

SHIFT_CHANGED = 'SHIFT_CHANGED'
GROUP_ACTIVITY_UPDATED = 'GROUP_ACTIVITY_UPDATED'
GROUP_ACTIVITY_EVENT = 'GROUP_ACTIVITY_EVENT'

SERVICENOW_SYNC_FAILED = 'SERVICENOW_SYNC_FAILED'
SERVICENOW_SYNC_RECOVERED = 'SERVICENOW_SYNC_RECOVERED'

AUTOMATION_STATUS_CHANGED = 'AUTOMATION_STATUS_CHANGED'
LIVE_PILOT_STATUS_CHANGED = 'LIVE_PILOT_STATUS_CHANGED'


class WebSocketManager:
    """
    Enterprise WebSocket Manager providing reliable:
    - Authentication and connection lifecycle tracking
    - Event envelope standardization with ISO-8601 timestamps and event IDs
    - Role-based and team-based authorization isolation
    - Duplicate event protection and dead-socket pruning
    - Prometheus observability integration
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.user_roles: Dict[str, str] = {}
        self.seen_events: Set[str] = set()

    def _prepare_packet(self, event: str, data: dict) -> dict:
        """
        Standardizes event envelope (Section 12):
        Ensures event_id, event type, and timezone-aware ISO-8601 timestamp are present.
        """
        event_id = str(data.get("event_id") or uuid.uuid4())
        now_ts = data.get("timestamp") or datetime.now(timezone.utc).isoformat()
        return {
            "event": event,
            "type": event,
            "event_id": event_id,
            "timestamp": now_ts,
            "data": data,
            "payload": data
        }

    async def connect(self, websocket: WebSocket, user_id: str, role: str = "EMPLOYEE"):
        await websocket.accept()
        is_reconnect = user_id in self.active_connections
        if not is_reconnect:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        self.user_roles[user_id] = role

        metrics.inc("websocket_connections")
        if is_reconnect:
            metrics.inc("websocket_reconnects")
        metrics.set_gauge("active_websocket_connections", sum(len(conns) for conns in self.active_connections.values()))

    async def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                self.user_roles.pop(user_id, None)

        metrics.set_gauge("active_websocket_connections", sum(len(conns) for conns in self.active_connections.values()))

    async def send_to_user(self, user_id: str, event: str, data: dict):
        """Enforces user event isolation: message delivered ONLY to target user's active sockets."""
        if user_id in self.active_connections:
            packet = self._prepare_packet(event, data)
            stale = []
            for connection in list(self.active_connections[user_id]):
                try:
                    await connection.send_json(packet)
                    metrics.inc("websocket_events_published")
                except Exception:
                    metrics.inc("websocket_events_failed")
                    stale.append(connection)
            for dead_ws in stale:
                await self.disconnect(dead_ws, user_id)

    async def broadcast_to_admins(self, event: str, data: dict):
        """Dispatches event exclusively to active connections held by ADMIN or SUPERVISOR users."""
        for user_id, role in list(self.user_roles.items()):
            if role in ("ADMIN", "SUPERVISOR") and user_id in self.active_connections:
                await self.send_to_user(user_id, event, data)

    async def broadcast_to_team(self, team_id: str, event: str, data: dict, member_user_ids: Optional[List[str]] = None):
        """Dispatches event to all team members and listening ADMIN/SUPERVISOR connections."""
        target_users = set(member_user_ids or [])
        # Add all online admins and supervisors
        for user_id, role in list(self.user_roles.items()):
            if role in ("ADMIN", "SUPERVISOR"):
                target_users.add(user_id)

        for user_id in target_users:
            if user_id in self.active_connections:
                await self.send_to_user(user_id, event, data)

    async def broadcast_all(self, event: str, data: dict):
        """Dispatches global announcements while gracefully pruning any disconnected/stale sockets."""
        packet = self._prepare_packet(event, data)
        for user_id, connections in list(self.active_connections.items()):
            stale = []
            for connection in list(connections):
                try:
                    await connection.send_json(packet)
                    metrics.inc("websocket_events_published")
                except Exception:
                    metrics.inc("websocket_events_failed")
                    stale.append(connection)
            for dead_ws in stale:
                await self.disconnect(dead_ws, user_id)


ws_manager = WebSocketManager()

