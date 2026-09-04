"""Pydantic schemas for account / people / request APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class SelectRoleRequest(BaseModel):
    role: str = Field(pattern="^(student|teacher)$")


class AccountTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str | None
    account_id: str
    public_id: str | None = None
    display_name: str = ""
    expires_at: str
    needs_role: bool = False


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    photo_base64: str | None = None


class LinkedTeacherSummary(BaseModel):
    public_id: str
    display_name: str


class AccountProfileResponse(BaseModel):
    account_id: str
    email: str | None
    display_name: str
    role: str | None
    public_id: str | None
    photo_base64: str | None = None
    needs_role: bool
    link_status: str = "independent"
    teacher: LinkedTeacherSummary | None = None
    invite_code: str | None = None


class PersonSummary(BaseModel):
    account_id: str
    public_id: str
    display_name: str
    role: str
    photo_base64: str | None = None


class SearchResponse(BaseModel):
    results: list[PersonSummary]


class SendRequestBody(BaseModel):
    to_public_id: str = Field(min_length=3, max_length=16)


class ConnectTeacherBody(BaseModel):
    teacher_code: str = Field(default="", max_length=16)
    teacher_id: str = Field(default="", max_length=16)

    def resolved_code(self) -> str:
        return (self.teacher_code or self.teacher_id or "").strip()


class RequestSummary(BaseModel):
    id: str
    kind: str
    from_public_id: str
    from_display_name: str
    to_public_id: str
    to_display_name: str
    status: str
    direction: str  # incoming | outgoing


class RequestListResponse(BaseModel):
    items: list[RequestSummary]
