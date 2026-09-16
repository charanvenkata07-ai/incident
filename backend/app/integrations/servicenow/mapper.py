from app.models.incident import Incident

class ServiceNowMapper:
    FIELD_MAP = {
        'number': 'incident_number',
        'sys_id': 'servicenow_sys_id',
        'short_description': 'short_description',
        'description': 'description',
        'priority': 'priority',
        'impact': 'impact',
        'urgency': 'urgency',
        'category': 'category',
        'subcategory': 'subcategory',
        'assignment_group.display_value': 'assignment_group',
        'assigned_to.display_value': 'assigned_to',
        'state': 'state',
        'opened_at': 'opened_at',
        'work_notes': 'work_notes',
    }
    
    def to_incident(self, payload: dict) -> dict:
        return {}
        
    def to_servicenow(self, incident: Incident) -> dict:
        return {}
        
    def map_priority(self, sn_priority) -> str:
        return "P1"
        
    def map_state(self, sn_state) -> str:
        return "NEW"
