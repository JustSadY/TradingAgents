from pydantic import BaseModel, ConfigDict


class ApiResponse(BaseModel):
    """Base for response models whose fields carry defaults.

    A Python default makes a field optional in the *validation* schema, and
    that is the schema FastAPI publishes. The generated TypeScript therefore
    marked `issues: string[] = []` as possibly-undefined, even though a
    response model always serialises every field — so the frontend either
    guarded a value that is always there or, more often, did not and relied on
    the type checker being lenient.

    Serialising is what a response model does, so the serialisation schema is
    the honest one to publish: there, a defaulted field is always present.

    Use this as the base for any response model with defaulted fields. Request
    bodies must keep plain `BaseModel` — their defaults really are optional,
    and FastAPI reads the validation schema for them.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


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
