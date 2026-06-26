from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import load_config


router = APIRouter()
router.prefix = "/api/test"
runtime_router = APIRouter()

_runtime_state: dict[str, Any] = {
    "long_token": None,
    "access_token": None,
    "jobs": {},
}


class VerifyRequest(BaseModel):
    serial_code: str
    secret_code: str


class LongTokenRequest(BaseModel):
    serial_number: str
    secret: str
    name: str
    version: str
    capabilities: list[str]


class PollRequest(BaseModel):
    status: str | None = None
    current_job_id: str | None = None
    force_no_job: bool = False


class ProgressRequest(BaseModel):
    progress: int
    message: str
    status: str


class CompleteRequest(BaseModel):
    status: str
    result: dict[str, Any] | None = None
    error_message: str | None = None


def _request_time() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _utc_timestamp(delta: timedelta) -> str:
    value = datetime.now(timezone.utc) + delta
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


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


def _success(data: Any, message: str = "success") -> dict[str, Any]:
    return {
        "message": message,
        "data": data,
    }


def _error(status_code: int, message: str, code: str, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "message": message,
            "data": data,
            "code": code,
        },
    )


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    token_type, _, token = authorization.partition(" ")
    if token_type.lower() != "bearer" or not token:
        return None

    return token


def _validate_serial_number(serial_number: str) -> JSONResponse | None:
    config = load_config()
    if serial_number != config.test_serial_number:
        return _error(404, "Device not found.", "DEVICE_NOT_FOUND")

    return None


def _validate_long_token(
    serial_number: str,
    authorization: str | None,
) -> JSONResponse | None:
    serial_error = _validate_serial_number(serial_number)
    if serial_error is not None:
        return serial_error

    if _bearer_token(authorization) != _runtime_state["long_token"]:
        return _error(401, "Device long token is invalid.", "DEVICE_LONG_TOKEN_INVALID")

    return None


def _validate_access_token(authorization: str | None) -> JSONResponse | None:
    if _bearer_token(authorization) != _runtime_state["access_token"]:
        return _error(401, "Device token is invalid.", "DEVICE_ACCESS_TOKEN_INVALID")

    return None


def _job_response(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job": {
            "public_id": job["public_id"],
            "status": job["status"],
            "progress": job["progress"],
            "progress_message": job.get("progress_message"),
            "error_message": job.get("error_message"),
            "result": job.get("result"),
            "finished_at": job.get("finished_at"),
        }
    }


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


@runtime_router.post("/api/device-auth/long-token")
def issue_long_token(payload: LongTokenRequest):
    config = load_config()
    if payload.serial_number != config.test_serial_number:
        return _error(404, "Device not found.", "DEVICE_NOT_FOUND")
    if payload.secret != config.test_secret:
        return _error(400, "Device secret is invalid.", "DEVICE_SECRET_INVALID")

    long_token = f"test-long-{uuid4().hex}"
    _runtime_state["long_token"] = long_token
    _runtime_state["access_token"] = None

    return _success(
        {
            "device_id": payload.serial_number,
            "long_token": long_token,
            "token_type": "Bearer",
            "expires_at": _utc_timestamp(timedelta(days=365)),
        },
        "設備長效 JWT 已發行。",
    )


@runtime_router.post("/api/devices/{serial_number}/access-tokens")
def issue_access_token(
    serial_number: str,
    authorization: str | None = Header(default=None),
):
    token_error = _validate_long_token(serial_number, authorization)
    if token_error is not None:
        return token_error

    access_token = f"test-access-{uuid4().hex}"
    _runtime_state["access_token"] = access_token

    return _success(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 900,
            "expires_at": _utc_timestamp(timedelta(minutes=15)),
        },
        "設備短效 JWT 已發行。",
    )


@runtime_router.post("/api/devices/{serial_number}/poll")
def poll_job(
    serial_number: str,
    payload: PollRequest,
    authorization: str | None = Header(default=None),
):
    serial_error = _validate_serial_number(serial_number)
    if serial_error is not None:
        return serial_error

    token_error = _validate_access_token(authorization)
    if token_error is not None:
        return token_error

    if payload.force_no_job:
        return Response(status_code=204)

    config = load_config()
    job_id = f"BAJ-{uuid4().hex[:12].upper()}"
    job = {
        "public_id": job_id,
        "status": "running",
        "progress": 0,
        "progress_message": None,
        "error_message": None,
        "result": None,
        "finished_at": None,
    }
    _runtime_state["jobs"][job_id] = job

    return _success(
        {
            "job_id": job_id,
            "type": "button_function",
            "payload": {
                "product_function_code": config.test_product_function_code,
            },
        }
    )


@runtime_router.post("/api/device-jobs/{job_id}/progress")
def report_progress(
    job_id: str,
    payload: ProgressRequest,
    authorization: str | None = Header(default=None),
):
    token_error = _validate_access_token(authorization)
    if token_error is not None:
        return token_error

    job = _runtime_state["jobs"].get(job_id)
    if job is None:
        return _error(404, "Device job not found.", "DEVICE_JOB_NOT_FOUND")
    if payload.progress < 0 or payload.progress > 100:
        return _error(422, "Validation failed.", "VALIDATION_ERROR")
    if len(payload.message) > 255:
        return _error(422, "Validation failed.", "VALIDATION_ERROR")

    job["status"] = payload.status
    job["progress"] = payload.progress
    job["progress_message"] = payload.message

    return _success(_job_response(job))


@runtime_router.post("/api/device-jobs/{job_id}/complete")
def complete_job(
    job_id: str,
    payload: CompleteRequest,
    authorization: str | None = Header(default=None),
):
    token_error = _validate_access_token(authorization)
    if token_error is not None:
        return token_error

    job = _runtime_state["jobs"].get(job_id)
    if job is None:
        return _error(404, "Device job not found.", "DEVICE_JOB_NOT_FOUND")
    if payload.status not in {"succeeded", "failed"}:
        return _error(422, "Validation failed.", "VALIDATION_ERROR")

    job["status"] = payload.status
    job["error_message"] = payload.error_message
    job["result"] = payload.result
    job["finished_at"] = _utc_timestamp(timedelta())
    if payload.status == "succeeded":
        job["progress"] = 100

    return _success(_job_response(job))
