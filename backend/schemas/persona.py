"""Response contract for investor personas."""

from pydantic import BaseModel


class PersonaRead(BaseModel):
    """A persona as the API returns it, built-in or user-created.

    The two sources are flattened into one shape so the client does not have to
    know which table a persona came from; `is_builtin` is what decides whether
    it can be edited or deleted.
    """

    key: str
    label: str
    description: str
    instructions: str
    is_builtin: bool

    @classmethod
    def from_row(cls, row, *, is_builtin: bool) -> "PersonaRead":
        return cls(
            key=row.key,
            label=row.label,
            description=row.description,
            instructions=row.instructions,
            is_builtin=is_builtin,
        )
