from datetime import datetime

from pydantic import BaseModel


class AssistantHistoryItem(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

class AssistantChatResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
