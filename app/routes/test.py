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


async def _request_json(request: Request) -> Any:
    try:
        return await request.json()
    except ValueError:
        return {}


def _requested_jobs(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    candidate = payload.get("jobs") or payload.get("job")
    if isinstance(candidate, dict):
        candidate = [candidate]
    if isinstance(candidate, list):
        return [item for item in candidate if isinstance(item, dict)]

    return []


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


@router.post("/jobs/request")
async def request_jobs(request: Request) -> dict[str, Any]:
    payload = await _request_json(request)
    jobs = _requested_jobs(payload)
    if not jobs:
        jobs = [
            {
                "id": f"test-touch-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "command": "Touch",
                "payload": {
                    "source": "api-test",
                },
            }
        ]

    return {
        "error": False,
        "data": {
            "remote_ip": _remote_ip(request),
            "request_time": _request_time(),
            "jobs": jobs,
        },
    }
