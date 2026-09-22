class MockServiceNowClient:
    async def get_incident(self, sys_id) -> dict:
        return {}
        
    async def update_incident(self, sys_id, fields, mode=None) -> dict:
        return {"status": "success", "sys_id": sys_id, "fields": fields}
        
    async def update_assignment(self, sys_id, assigned_to, mode=None) -> dict:
        return {"status": "success", "sys_id": sys_id, "assigned_to": assigned_to}

    async def update_state(self, sys_id, state, mode=None) -> dict:
        return {"status": "success", "sys_id": sys_id, "state": state}

    async def add_work_note(self, sys_id, note, mode=None) -> dict:
        return {"status": "success", "sys_id": sys_id, "work_notes": note}
        
    async def generate_incident(self) -> dict:
        return {"number": "INC0010010", "short_description": "Test incident", "priority": "1"}
