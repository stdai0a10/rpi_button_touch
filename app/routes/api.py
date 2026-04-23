from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter

from app.config import load_config


router = APIRouter()


def _verify_url(service_url: str) -> str:
    return f"{service_url.rstrip('/')}/verify"


def _parse_json_body(raw_body: str) -> Any:
    if not raw_body:
        return None

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body


def _verification_payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}

    data = body.get("data")
    if isinstance(data, dict):
        return data

    return body


def _read_service_verify(
    service_url: str,
    service_token: str,
    serial_code: str,
    secret_code: str,
) -> dict[str, bool]:
    if not service_url:
        return {
            "connection": False,
            "verified": False,
            "blocked": False,
        }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if service_token:
        headers["Authorization"] = f"Bearer {service_token}"

    url = _verify_url(service_url)
    payload = json.dumps(
        {
            "serial_code": serial_code,
            "secret_code": secret_code,
        }
    ).encode("utf-8")
    request = UrlRequest(url, data=payload, headers=headers, method="POST")

    try:
        with urlopen(request, timeout=10) as response:
            raw_body = response.read().decode("utf-8")
            body = _parse_json_body(raw_body)
            payload = _verification_payload(body)

            return {
                "connection": True,
                "verified": bool(payload.get("verified", False)),
                "blocked": bool(payload.get("blocked", False)),
            }
    except HTTPError as error:
        raw_body = error.read().decode("utf-8", errors="replace")
        body = _parse_json_body(raw_body)
        payload = _verification_payload(body)

        return {
            "connection": True,
            "verified": bool(payload.get("verified", False)),
            "blocked": bool(payload.get("blocked", False)),
        }
    except (OSError, URLError):
        return {
            "connection": False,
            "verified": False,
            "blocked": False,
        }


@router.post("/api/touch")
def touch() -> dict[str, bool]:
    return {"error": False}


@router.get("/api/info")
def info() -> dict[str, Any]:
    config = load_config()
    service_verify = _read_service_verify(
        config.service_url,
        config.service_token,
        config.serial_code,
        config.secret_code,
    )

    return {
        "error": False,
        "data": {
            "serial_code": config.serial_code,
            "connection": service_verify["connection"],
            "verified": service_verify["verified"],
            "blocked": service_verify["blocked"],
        },
    }
