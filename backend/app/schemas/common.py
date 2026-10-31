from typing import Optional
from pydantic import BaseModel

class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    audit_event_id: Optional[str] = None
