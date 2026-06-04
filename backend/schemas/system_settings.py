from datetime import datetime
from pydantic import BaseModel


class SystemSettingsRead(BaseModel):
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SystemSettingsUpdate(BaseModel):
    pass
