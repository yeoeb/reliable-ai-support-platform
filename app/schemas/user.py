from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    email: EmailStr
    display_name: str = Field(
        min_length=1,
        max_length=100,
    )

    password: str = Field(
        min_length=12,
        max_length=128,
    )


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime