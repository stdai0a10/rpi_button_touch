from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from app.config import AppConfig, load_config
from app.gpio import configured_function_codes, execute_function, execute_touch, product_code


LOGGER = logging.getLogger(__name__)
_JOB_LOCK = threading.Lock()


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


def _jobs_request_url(service_url: str) -> str:
    return f"{service_url.rstrip('/')}/jobs/request"


def _parse_json_body(raw_body: str) -> Any:
    if not raw_body:
        return None

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body


def _service_headers(config: AppConfig) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if config.service_token:
        headers["Authorization"] = f"Bearer {config.service_token}"

    return headers


def _job_request_payload(config: AppConfig) -> dict[str, Any]:
    capabilities = configured_function_codes()

    return {
        "serial_code": config.serial_code,
        "secret_code": config.secret_code,
        "product_code": product_code(),
        "runner": {
            "name": "rpi-button-touch",
            "version": "1",
        },
        "capabilities": capabilities,
        "requested_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _payload_data(body: Any) -> Any:
    if isinstance(body, dict) and "data" in body:
        return body["data"]

    return body


def _extract_jobs(body: Any) -> list[dict[str, Any]]:
    data = _payload_data(body)
    candidate: Any

    if isinstance(data, dict):
        candidate = data.get("jobs", data.get("job", []))
    else:
        candidate = data

    if isinstance(candidate, dict):
        candidate = [candidate]
    if not isinstance(candidate, list):
        return []

    return [item for item in candidate if isinstance(item, dict)]


def request_jobs(config: AppConfig | None = None) -> list[dict[str, Any]]:
    config = config or load_config()
    if not config.service_url:
        return []

    payload = json.dumps(_job_request_payload(config)).encode("utf-8")
    request = UrlRequest(
        _jobs_request_url(config.service_url),
        data=payload,
        headers=_service_headers(config),
        method="POST",
    )

    with urlopen(request, timeout=config.job_request_timeout_seconds) as response:
        body = _parse_json_body(response.read().decode("utf-8"))

    return _extract_jobs(body)


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


def execute_job(job: dict[str, Any]) -> JobExecutionResult:
    command = str(
        job.get("command") or job.get("type") or job.get("action") or job.get("name") or ""
    )
    job_id = job.get("id")
    job_id_text = str(job_id) if job_id is not None else None

    function_code = _job_function_code(job)
    if function_code is not None:
        results = execute_function(function_code)
        if len(results) == 1:
            data = asdict(results[0])
            data["function_code"] = function_code

            return JobExecutionResult(
                job_id=job_id_text,
                command=results[0].command,
                success=True,
                data=data,
            )

        return JobExecutionResult(
            job_id=job_id_text,
            command=function_code,
            success=True,
            data={
                "function_code": function_code,
                "jobs": [asdict(result) for result in results],
            },
        )

    if command.lower() != "touch":
        return JobExecutionResult(
            job_id=job_id_text,
            command=command or "unknown",
            success=False,
            data={},
            error=f"Unsupported command: {command or 'unknown'}",
        )

    touch_result = execute_touch()
    return JobExecutionResult(
        job_id=job_id_text,
        command="Touch",
        success=True,
        data=asdict(touch_result),
    )


def _failed_job_result(job: dict[str, Any], error: Exception) -> JobExecutionResult:
    command = str(
        job.get("command") or job.get("type") or job.get("action") or job.get("name") or ""
    )
    job_id = job.get("id")

    return JobExecutionResult(
        job_id=str(job_id) if job_id is not None else None,
        command=command or "unknown",
        success=False,
        data={},
        error=str(error),
    )


def poll_and_run_jobs(config: AppConfig | None = None) -> JobPollResult:
    config = config or load_config()
    if not config.service_url:
        return JobPollResult(
            connection=False,
            jobs_received=0,
            jobs_executed=0,
            results=[],
            error="SERVICE_URL is not configured",
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
        jobs = request_jobs(config)
        results: list[JobExecutionResult] = []
        for job in jobs:
            try:
                results.append(execute_job(job))
            except Exception as error:
                LOGGER.exception("Job execution failed")
                results.append(_failed_job_result(job, error))

        executed = sum(1 for result in results if result.success)

        return JobPollResult(
            connection=True,
            jobs_received=len(jobs),
            jobs_executed=executed,
            results=results,
        )
    except HTTPError as error:
        LOGGER.warning("Job request failed with HTTP %s", error.code)
        return JobPollResult(
            connection=True,
            jobs_received=0,
            jobs_executed=0,
            results=[],
            error=f"HTTP {error.code}",
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
