from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = PROJECT_ROOT / "data" / "secrets.json"


@dataclass(frozen=True)
class AppConfig:
    serial_code: str
    secret_code: str
    service_url: str
    service_token: str


def _non_empty_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    value = value.strip()
    return value or None


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
        serial_code=str(secrets.get("serial_code", "")),
        secret_code=str(secrets.get("secret_code", "")),
        service_url=_non_empty_env("SERVICE_URL") or str(secrets.get("service_url", "")),
        service_token=(
            _non_empty_env("SERVICE_TOKEN") or str(secrets.get("service_token", ""))
        ),
    )
