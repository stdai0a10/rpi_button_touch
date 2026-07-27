from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from app.config import AppConfig, load_config
from app.gpio import configured_function_codes, execute_function, product_code


LOGGER = logging.getLogger(__name__)
_JOB_LOCK = threading.Lock()
_TOKEN_LOCK = threading.Lock()


@dataclass
class DeviceTokenState:
    long_token: str | None = None
    access_token: str | None = None


@dataclass(frozen=True)
class DeviceApiError(Exception):
    status_code: int
    message: str
    code: str | None = None
    method: str | None = None
    url: str | None = None

    def __str__(self) -> str:
        status = str(self.status_code)
        if self.code:
            status = f"{status} {self.code}"

        detail = f"{status}: {self.message}"
        if self.method or self.url:
            return f"{self.method or '???'} {self.url or '?'} returned {detail}"

        return detail


@dataclass(frozen=True)
class JobExecutionResult:
    job_id: str | None
    command: str
    success: bool
    data: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class JobPollResult:
    connection: bool
    jobs_received: int
    jobs_executed: int
    results: list[JobExecutionResult]
    error: str | None = None


_TOKEN_STATE = DeviceTokenState()


def _api_url(config: AppConfig, path: str) -> str:
    return f"{config.service_api_url.rstrip('/')}/{path.lstrip('/')}"


def _parse_json_body(raw_body: str) -> Any:
    if not raw_body:
        return None

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body


def _response_data(body: Any) -> Any:
    if isinstance(body, dict):
        return body.get("data")

    return None


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def _post_json(
    config: AppConfig,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request_url = _api_url(config, path)
    request = UrlRequest(
        request_url,
        data=data,
        headers=_headers(token),
        method="POST",
    )

    try:
        with urlopen(request, timeout=config.job_request_timeout_seconds) as response:
            if response.status == 204:
                return None

            raw_body = response.read().decode("utf-8")
            return _parse_json_body(raw_body)
    except HTTPError as error:
        raw_body = error.read().decode("utf-8", errors="replace")
        body = _parse_json_body(raw_body)
        message = str(error)
        code = None

        LOGGER.debug('%r\n%s', error, raw_body)

        if isinstance(body, dict):
            message = str(body.get("message") or message)
            raw_code = body.get("code")
            code = str(raw_code) if raw_code is not None else None

        raise DeviceApiError(
            error.code,
            message,
            code,
            method=request.get_method(),
            url=str(error.url or request_url),
        ) from error


def _request_long_token(config: AppConfig) -> str:
    body = _post_json(
        config,
        "/device-auth/long-token",
        {
            # "name": config.name,
            # "version": config.version,
            "serial_number": config.serial_code,
            "secret": config.secret_code,
            # "capabilities": configured_function_codes(),
        },
    )
    data = _response_data(body)
    if not isinstance(data, dict) or not data.get("long_token"):
        raise DeviceApiError(502, "Long token response is invalid")

    return str(data["long_token"])


def _request_access_token(config: AppConfig, long_token: str) -> str:
    body = _post_json(
        config,
        f"/devices/{config.serial_code}/access-tokens",
        token=long_token,
    )
    data = _response_data(body)
    if not isinstance(data, dict) or not data.get("access_token"):
        raise DeviceApiError(502, "Access token response is invalid")

    return str(data["access_token"])


def _ensure_access_token(config: AppConfig, force_refresh: bool = False) -> str:
    with _TOKEN_LOCK:
        if force_refresh:
            _TOKEN_STATE.access_token = None

        if _TOKEN_STATE.access_token:
            return _TOKEN_STATE.access_token

        if not _TOKEN_STATE.long_token:
            _TOKEN_STATE.long_token = _request_long_token(config)

        try:
            _TOKEN_STATE.access_token = _request_access_token(
                config, _TOKEN_STATE.long_token
            )
        except DeviceApiError as error:
            if error.code != "DEVICE_LONG_TOKEN_INVALID":
                raise

            _TOKEN_STATE.long_token = _request_long_token(config)
            _TOKEN_STATE.access_token = _request_access_token(
                config, _TOKEN_STATE.long_token
            )

        return _TOKEN_STATE.access_token


def _poll_job(config: AppConfig, access_token: str) -> dict[str, Any] | None:
    LOGGER.info("Polling device jobs")

    body = _post_json(
        config,
        f"/devices/{config.serial_code}/poll",
        {
            "status": "idle",
            "current_job_id": None,
        },
        token=access_token,
    )
    if body is None:
        LOGGER.debug("Device job poll returned no content")
        return None

    data = _response_data(body)
    if data is None:
        LOGGER.debug("Device job poll returned no job")
        return None
    if not isinstance(data, dict):
        raise DeviceApiError(502, "Poll response data must be an object")

    LOGGER.info("Device job poll returned job: %s", _job_id(data) or "unknown")
    return data


def request_jobs(config: AppConfig | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    if not config.service_api_url:
        return []

    access_token = _ensure_access_token(config)
    try:
        job = _poll_job(config, access_token)
    except DeviceApiError as error:
        if error.code != "DEVICE_ACCESS_TOKEN_INVALID":
            raise

        access_token = _ensure_access_token(config, force_refresh=True)
        job = _poll_job(config, access_token)

    return [job] if job else []


def _post_access_json(
    config: AppConfig,
    path: str,
    payload: dict[str, Any],
    access_token: str,
) -> tuple[Any, str]:
    try:
        return _post_json(config, path, payload, token=access_token), access_token
    except DeviceApiError as error:
        if error.code != "DEVICE_ACCESS_TOKEN_INVALID":
            raise

        refreshed_token = _ensure_access_token(config, force_refresh=True)
        return (
            _post_json(config, path, payload, token=refreshed_token),
            refreshed_token,
        )


def _job_id(job: dict[str, Any]) -> str | None:
    job_id = job.get("job_id") or job.get("public_id") or job.get("id")
    return str(job_id) if job_id is not None else None


def _job_function_code(job: dict[str, Any]) -> str | None:
    payload = job.get("payload")
    value: Any = None

    if isinstance(payload, dict):
        value = payload.get("product_function_code")
    if value is None:
        value = job.get("product_function_code")

    if value is None:
        return None

    function_code = str(value).strip()
    return function_code or None


def _report_progress(
    config: AppConfig,
    access_token: str,
    job_id: str,
    progress: int,
    message: str,
) -> str:
    _, access_token = _post_access_json(
        config,
        f"/device-jobs/{job_id}/progress",
        {
            "progress": progress,
            "message": message[:255],
            "status": "running",
        },
        access_token,
    )

    return access_token


def _report_complete(
    config: AppConfig,
    access_token: str,
    job_id: str,
    payload: dict[str, Any],
) -> str:
    _, access_token = _post_access_json(
        config,
        f"/device-jobs/{job_id}/complete",
        payload,
        access_token,
    )

    return access_token


def _complete_failed(
    config: AppConfig,
    access_token: str,
    job_id: str | None,
    message: str,
) -> str:
    if not job_id:
        return access_token

    return _report_complete(
        config,
        access_token,
        job_id,
        {
            "status": "failed",
            "error_message": message[:255],
        },
    )


def execute_job(
    job: dict[str, Any],
    config: AppConfig | None = None,
    access_token: str | None = None,
) -> JobExecutionResult:
    config = config or load_config()
    access_token = access_token or _ensure_access_token(config)
    job_id = _job_id(job)
    function_code = _job_function_code(job)
    command = function_code or str(job.get("type") or job.get("command") or "unknown")

    if not job_id:
        return JobExecutionResult(
            job_id=None,
            command=command,
            success=False,
            data={},
            error="Job id is missing",
        )
    if not function_code:
        message = "Job payload.product_function_code is missing"
        _complete_failed(config, access_token, job_id, message)
        return JobExecutionResult(
            job_id=job_id,
            command=command,
            success=False,
            data={},
            error=message,
        )

    start_time = time.monotonic()
    try:
        access_token = _report_progress(
            config, access_token, job_id, 10, "Function started"
        )
        results = execute_function(function_code)
        duration_ms = round((time.monotonic() - start_time) * 1000)
        data = {
            "function_code": function_code,
            "product_code": product_code(),
            "duration_ms": duration_ms,
            "jobs": [asdict(result) for result in results],
        }
        access_token = _report_complete(
            config,
            access_token,
            job_id,
            {
                "status": "succeeded",
                "result": data,
            },
        )

        return JobExecutionResult(
            job_id=job_id,
            command=function_code,
            success=True,
            data=data,
        )
    except Exception as error:
        try:
            _complete_failed(config, access_token, job_id, str(error))
        except Exception:
            LOGGER.exception("Failed to report job failure")

        raise


def _failed_job_result(
    job: dict[str, Any],
    error: Exception,
) -> JobExecutionResult:
    return JobExecutionResult(
        job_id=_job_id(job),
        command=(
            _job_function_code(job)
            or str(job.get("type") or job.get("command") or "unknown")
        ),
        success=False,
        data={},
        error=str(error),
    )


def poll_and_run_jobs(config: AppConfig | None = None) -> JobPollResult:
    config = config or load_config()
    if not config.service_api_url:
        return JobPollResult(
            connection=False,
            jobs_received=0,
            jobs_executed=0,
            results=[],
            error="SERVICE_API_URL is not configured",
        )

    if not _JOB_LOCK.acquire(blocking=False):
        return JobPollResult(
            connection=True,
            jobs_received=0,
            jobs_executed=0,
            results=[],
            error="Another job poll is already running",
        )

    try:
        LOGGER.info(
            "Job poll tick started for serial %s with %s second interval",
            config.serial_code,
            config.job_request_interval_seconds,
        )
        jobs = request_jobs(config)
        access_token = _ensure_access_token(config)
        results: list[JobExecutionResult] = []
        for job in jobs:
            try:
                results.append(execute_job(job, config, access_token))
            except Exception as error:
                LOGGER.exception("Job execution failed")
                results.append(_failed_job_result(job, error))

        executed = sum(1 for result in results if result.success)
        LOGGER.info(
            "Job poll tick finished: received=%s executed=%s",
            len(jobs),
            executed,
        )

        return JobPollResult(
            connection=True,
            jobs_received=len(jobs),
            jobs_executed=executed,
            results=results,
        )
    except (OSError, URLError) as error:
        LOGGER.warning("Job service is unreachable: %s", error)
        return JobPollResult(
            connection=False,
            jobs_received=0,
            jobs_executed=0,
            results=[],
            error=str(error),
        )
    except DeviceApiError as error:
        LOGGER.warning("Device API failed: %s", error)
        return JobPollResult(
            connection=True,
            jobs_received=0,
            jobs_executed=0,
            results=[],
            error=str(error),
        )
    except Exception as error:
        LOGGER.exception("Job polling failed")
        return JobPollResult(
            connection=True,
            jobs_received=0,
            jobs_executed=0,
            results=[],
            error=str(error),
        )
    finally:
        _JOB_LOCK.release()
