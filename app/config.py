from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = PROJECT_ROOT / "data" / "secrets.json"
RPI_CONFIG_PATH = PROJECT_ROOT / "data" / "rpi.json"


@dataclass(frozen=True)
class AppConfig:
    app_name: str
    app_version: str
    serial_code: str
    secret_code: str
    service_url: str
    service_token: str
    job_runner_enabled: bool
    job_request_interval_seconds: int
    job_request_timeout_seconds: int
    test_serial_number: str
    test_secret: str
    test_product_function_code: str


def _non_empty_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    value = value.strip()
    return value or None


def _env_bool(name: str, default: bool) -> bool:
    value = _non_empty_env(name)
    if value is None:
        return default

    return value.lower() in {"1", "true", "yes", "on"}


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}

    return bool(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    value = _non_empty_env(name)
    if value is None:
        return default

    try:
        parsed = int(value)
    except ValueError:
        return default

    return max(minimum, parsed)


def _read_secrets(path: Path = SECRETS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")

    return data


def load_config() -> AppConfig:
    load_dotenv(PROJECT_ROOT / ".env")
    secrets = _read_secrets()

    return AppConfig(
        app_name=(
            _non_empty_env("APP_NAME")
            or str(secrets.get("app_name", "rpi-button-touch"))
        ),
        app_version=(
            _non_empty_env("APP_VERSION") or str(secrets.get("app_version", "1.0.0"))
        ),
        serial_code=_non_empty_env("SERIAL_CODE") or str(secrets.get("serial_code", "")),
        secret_code=_non_empty_env("SECRET_CODE") or str(secrets.get("secret_code", "")),
        service_url=_non_empty_env("SERVICE_URL") or str(secrets.get("service_url", "")),
        service_token=(
            _non_empty_env("SERVICE_TOKEN") or str(secrets.get("service_token", ""))
        ),
        job_runner_enabled=_env_bool(
            "JOB_RUNNER_ENABLED", _as_bool(secrets.get("job_runner_enabled"), False)
        ),
        job_request_interval_seconds=_env_int(
            "JOB_REQUEST_INTERVAL_SECONDS",
            _as_int(secrets.get("job_request_interval_seconds"), 15),
        ),
        job_request_timeout_seconds=_env_int(
            "JOB_REQUEST_TIMEOUT_SECONDS",
            _as_int(secrets.get("job_request_timeout_seconds"), 10),
        ),
        test_serial_number=(
            _non_empty_env("TEST_SERIAL_NUMBER")
            or str(secrets.get("test_serial_number", "TEST0001"))
        ),
        test_secret=(
            _non_empty_env("TEST_SECRET") or str(secrets.get("test_secret", "TEST0001"))
        ),
        test_product_function_code=(
            _non_empty_env("TEST_PRODUCT_FUNCTION_CODE")
            or str(
                secrets.get("test_product_function_code", "PFN-WRKWI2STAEYU")
            )
        ),
    )
