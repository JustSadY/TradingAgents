from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PresetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    settings_json: str


class PresetRead(BaseModel):
    id: int
    name: str
    description: str
    settings_json: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
