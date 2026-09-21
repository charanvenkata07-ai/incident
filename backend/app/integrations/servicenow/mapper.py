from datetime import datetime
from app.models.incident import Incident

class ServiceNowMapper:
    """
    Bi-directional field mapper between ServiceNow Table API representations
    and IncidentFlow domain models.
    """
    PRIORITY_MAP_TO_APP = {
        "1": "P1",
        "2": "P2",
        "3": "P3",
        "4": "P4",
        "1 - Critical": "P1",
        "2 - High": "P2",
        "3 - Moderate": "P3",
        "4 - Low": "P4",
    }

    STATE_MAP_TO_APP = {
        "1": "NEW",
        "2": "IN_PROGRESS",
        "3": "ON_HOLD",
        "6": "RESOLVED",
        "7": "CLOSED",
        "8": "CANCELED",
        "New": "NEW",
        "In Progress": "IN_PROGRESS",
        "Resolved": "RESOLVED",
        "Closed": "CLOSED"
    }

    def _extract_display_value(self, val) -> str | None:
        """Helper to extract display_value whether ServiceNow sends a reference dict or string."""
        if isinstance(val, dict):
            return val.get("display_value") or val.get("name") or val.get("value")
        return str(val) if val is not None else None

    def map_priority(self, sn_priority) -> str:
        """Normalizes ServiceNow priority to P1-P4."""
        if not sn_priority:
            return "P3"
        return self.PRIORITY_MAP_TO_APP.get(str(sn_priority).strip(), "P3")

    def map_state(self, sn_state) -> str:
        """Normalizes ServiceNow state to IncidentFlow state."""
        if not sn_state:
            return "NEW"
        return self.STATE_MAP_TO_APP.get(str(sn_state).strip(), "NEW")

    def to_incident(self, payload: dict) -> dict:
        """Converts incoming ServiceNow incident payload into IncidentFlow dictionary."""
        number = payload.get("number") or payload.get("incident_number") or ""
        sys_id = payload.get("sys_id") or payload.get("servicenow_sys_id") or ""
        
        opened_at_val = payload.get("opened_at")
        opened_at = None
        if isinstance(opened_at_val, datetime):
            opened_at = opened_at_val
        elif isinstance(opened_at_val, str):
            try:
                opened_at = datetime.fromisoformat(opened_at_val.replace("Z", "+00:00"))
            except Exception:
                opened_at = None

        return {
            "incident_number": number,
            "servicenow_sys_id": sys_id,
            "short_description": payload.get("short_description") or "Untitled Incident",
            "description": payload.get("description") or "",
            "priority": self.map_priority(payload.get("priority")),
            "impact": str(payload.get("impact")) if payload.get("impact") else None,
            "urgency": str(payload.get("urgency")) if payload.get("urgency") else None,
            "category": payload.get("category"),
            "subcategory": payload.get("subcategory"),
            "assignment_group": self._extract_display_value(payload.get("assignment_group")),
            "assigned_to": self._extract_display_value(payload.get("assigned_to")),
            "caller": self._extract_display_value(payload.get("caller_id") or payload.get("caller")),
            "location": self._extract_display_value(payload.get("location")),
            "configuration_item": self._extract_display_value(payload.get("cmdb_ci")),
            "state": self.map_state(payload.get("state")),
            "work_instructions": payload.get("u_work_instructions") or payload.get("work_instructions"),
            "work_notes": payload.get("work_notes") or payload.get("u_work_notes"),
            "additional_comments": payload.get("comments") or payload.get("additional_comments"),
            "opened_at": opened_at,
        }

    def to_servicenow(self, incident: Incident) -> dict:
        """Prepares an outgoing payload for ServiceNow Table API."""
        return {
            "short_description": incident.short_description,
            "state": incident.state,
            "work_notes": incident.work_notes
        }
