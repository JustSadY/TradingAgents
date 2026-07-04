from pydantic import BaseModel


class WebhookDeliveryRead(BaseModel):
    id: int
    event: str
    url: str
    success: bool
    status_code: int | None = None
    error: str | None = None
    created_at: str
