"""api.health — §26 "Server Health / Version"."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

_API_VERSION = "v1"

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    api_version: str
    server_time: datetime


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", api_version=_API_VERSION, server_time=datetime.now(timezone.utc))
