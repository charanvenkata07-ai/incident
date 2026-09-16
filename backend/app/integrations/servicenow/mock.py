class MockServiceNowClient:
    async def get_incident(self, sys_id) -> dict:
        return {}
        
    async def update_incident(self, sys_id, fields) -> dict:
        return {}
        
    async def update_assignment(self, sys_id, assigned_to) -> dict:
        return {}
        
    async def generate_incident(self) -> dict:
        return {"number": "INC0010010", "short_description": "Test incident", "priority": "1"}
