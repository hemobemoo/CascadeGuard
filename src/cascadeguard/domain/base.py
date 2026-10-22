from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base for all domain models: immutable and strict about unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")
