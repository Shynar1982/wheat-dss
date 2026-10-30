from pydantic import BaseModel, Field as PydField
from typing import Any

class FieldCreate(BaseModel):
    name: str = PydField(min_length=1, max_length=200)
    geom: dict[str, Any]

class FieldRead(BaseModel):
    field_id: int
    name: str
    area_ha: float | None
    geom: dict[str, Any]

    class Config:
        from_attributes = True
