from datetime import datetime

from pydantic import BaseModel, ConfigDict

class LogRead(BaseModel):
    id: int
    level: str
    source: str
    message: str
    details: str | None
    user_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
