from pydantic import BaseModel


class MessageResponse(BaseModel):
    detail: str


class IdResponse(BaseModel):
    id: int


class EarningsCalendarResponse(BaseModel):
    results: list


class SectorRotationResponse(BaseModel):
    sectors: list
    count: int


class DeleteResponse(BaseModel):
    deleted: bool


class OkResponse(BaseModel):
    ok: bool
