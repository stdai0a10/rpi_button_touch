from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = PROJECT_ROOT / "data" / "secrets.json"
APP_CONFIG_PATH = PROJECT_ROOT / "data" / "app.json"


@dataclass(frozen=True)
class AppConfig:
    name: str
    version: str
    env: str
    debug: bool
    serial_code: str
    secret_code: str
    service_api_url: str
    job_runner_enabled: bool
    job_request_interval_seconds: int
    job_request_timeout_seconds: int
    simulate_gpio: bool
    test_mode: bool
    test_serial_code: str
    test_secret_code: str
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
    serial_code = _non_empty_env("SERIAL_CODE") or secrets.get("serial_code", "")
    secret_code = _non_empty_env("SECRET_CODE") or secrets.get("secret_code", "")
    service_api_url = _non_empty_env("SERVICE_API_URL") or secrets.get(
        "service_api_url", "http://localhost:8000/api/test"
    )

    return AppConfig(
        name=_non_empty_env("APP_NAME") or "rpi-button-touch",
        version=_non_empty_env("APP_VERSION") or "1.0.0",
        env=_non_empty_env("APP_ENV") or "production",
        debug=_env_bool("APP_DEBUG", False),
        serial_code=serial_code,
        secret_code=secret_code,
        service_api_url=service_api_url,
        job_runner_enabled=_env_bool("JOB_RUNNER_ENABLED", True),
        job_request_interval_seconds=_env_int("JOB_REQUEST_INTERVAL_SECONDS", 15),
        job_request_timeout_seconds=_env_int("JOB_REQUEST_TIMEOUT_SECONDS", 10),
        simulate_gpio=_env_bool("SIMULATE_GPIO", False),
        test_mode=_env_bool("TEST_MODE", False),
        test_serial_code=_non_empty_env("TEST_SERIAL_CODE") or serial_code,
        test_secret_code=_non_empty_env("TEST_SECRET_CODE") or secret_code,
        test_product_function_code=(
            _non_empty_env("TEST_PRODUCT_FUNCTION_CODE") or "PFN-MIRAICHANKWI"
        ),
    )
