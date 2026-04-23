from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import load_config


router = APIRouter()
router.prefix = "/api/test"


class VerifyRequest(BaseModel):
    serial_code: str
    secret_code: str


def _request_time() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _remote_ip(request: Request) -> str | None:
    if request.client is None:
        return None

    return request.client.host


@router.post("/verify")
def verify(payload: VerifyRequest, request: Request) -> dict[str, Any]:
    config = load_config()
    verified = (
        payload.serial_code == config.serial_code
        and payload.secret_code == config.secret_code
    )

    return {
        "error": False,
        "data": {
            "remote_ip": _remote_ip(request),
            "request_time": _request_time(),
            "verified": verified,
            "blocked": False,
        },
    }
