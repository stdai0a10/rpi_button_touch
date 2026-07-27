from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Any

from app.config import APP_CONFIG_PATH, load_config


@unique
class ResourceType(StrEnum):
    GPIO = "GPIO"
    TIME = "TIME"


@unique
class ResourceMode(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


@unique
class ResourceState(StrEnum):
    HIGH = "high"
    LOW = "low"
    KEEP = "keep"
    RESET = "reset"


class RpiConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TouchResult:
    command: str
    simulated: bool
    steps: list[dict[str, Any]]


@dataclass(frozen=True)
class GpioUse:
    name: str
    type: str
    pin: int
    mode: str
    state: str
    final: str


_GPIO_SERVICE: GpioService | None = None
_GPIO_SERVICE_LOCK = threading.Lock()


def _read_rpi_config(path: Path = APP_CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise RpiConfigError(f"{path} must contain a JSON object")

    return data


def _gpio_number_from_label(label: str) -> int:
    prefix = "GPIO "
    if not label.startswith(prefix):
        raise RpiConfigError(f"Unsupported GPIO label: {label}")

    try:
        return int(label.removeprefix(prefix))
    except ValueError as error:
        raise RpiConfigError(f"Unsupported GPIO label: {label}") from error


def _state_value(state: str) -> int:
    normalized = state.strip().lower()
    if normalized == "high":
        return 1
    if normalized == "low":
        return 0

    raise RpiConfigError(f"Unsupported GPIO state: {state}")


def _pin_number(value: Any, context: str) -> int:
    try:
        pin = int(value)
    except (TypeError, ValueError) as error:
        raise RpiConfigError(f"{context} must be a GPIO pin number") from error

    if pin < 0:
        raise RpiConfigError(f"{context} must be a GPIO pin number")

    return pin


def _normalize_gpio_config(gpio_config: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(gpio_config, dict):
        raise RpiConfigError("GPIO config must be an object")

    normalized: dict[int, dict[str, Any]] = {}
    for raw_pin, config in gpio_config.items():
        pin = _pin_number(raw_pin, f"GPIO key {raw_pin!r}")
        if not isinstance(config, dict):
            raise RpiConfigError(f"GPIO.{raw_pin} config must be an object")

        normalized[pin] = config

    return normalized


def _command_name(job_name: str) -> str:
    return job_name.replace("_", " ").replace("-", " ").title().replace(" ", "")


def _parse_job_uses(
    job: dict[str, Any], gpio_config: dict[int, dict[str, Any]]
) -> dict[str, GpioUse]:
    uses = job.get("uses", [])

    if not isinstance(uses, list):
        raise RpiConfigError("job.uses must be a list")

    parsed: dict[str, GpioUse] = {}
    for index, item in enumerate(uses):
        if isinstance(item, str):
            name = item
            resource_type = ResourceType.GPIO
            pin = _gpio_number_from_label(item)
            final = ResourceState.RESET
        elif isinstance(item, dict):
            resource_type = str(item.get("type", "")).upper()

            name = str(item.get("name", "")).strip()
            if not name:
                raise RpiConfigError(f"job.uses[{index}].name is required")

            if resource_type == ResourceType.GPIO:
                pin = _pin_number(item.get("value"), f"job.uses[{index}].value")
            elif resource_type == ResourceType.TIME:
                pin = -1
            else:
                raise RpiConfigError(f"job.uses[{index}].type is unsupported")

            final = str(item.get("final", ResourceState.RESET)).lower()
        else:
            raise RpiConfigError("job.uses must contain GPIO resource objects")

        if pin in gpio_config:
            mode = str(gpio_config[pin].get("mode", ResourceMode.OUTPUT)).lower()
            state = str(gpio_config[pin].get("state", ResourceState.LOW)).lower()
        elif resource_type == ResourceType.TIME:
            mode = ResourceMode.INPUT
            state = ResourceState.LOW
        else:
            raise RpiConfigError(f"{name} references undeclared GPIO pin {pin}")

        if name in parsed:
            raise RpiConfigError(f"Duplicate job use name: {name}")

        parsed[name] = GpioUse(
            name=name, type=resource_type, pin=pin, mode=mode, state=state, final=final
        )

    return parsed


def _parse_job_actions(
    job: dict[str, Any], uses: dict[str, GpioUse]
) -> list[dict[str, Any]]:
    actions = job.get("actions") or job.get("action") or []

    if not isinstance(actions, list):
        raise RpiConfigError("job.actions must be a list of action objects")

    parsed = []
    for idx, item in enumerate(actions):
        if not isinstance(item, dict):
            raise RpiConfigError(f"job.actions[{idx}] must be a action object")

        key = item.get("use") or next(filter(lambda i: i in uses, item.keys()), None)
        if key not in uses:
            raise RpiConfigError(f"job.actions[{idx}] must reference a use")

        val = item["set"] if "set" in item else item.get(key)
        if val is None:
            raise RpiConfigError(f"job.actions[{idx}] must have a valid value")

        parsed.append({"use": key, "set": val})

    return parsed


def _job_config(rpi_config: dict[str, Any], job_name: str) -> dict[str, Any]:
    jobs = rpi_config.get("job", {})
    if not isinstance(jobs, dict):
        raise RpiConfigError("job config must be an object")

    config = jobs.get(job_name)
    if not isinstance(config, dict):
        raise RpiConfigError(f"job.{job_name} config must be an object")

    return config


def _function_jobs(rpi_config: dict[str, Any], function_code: str) -> list[str]:
    functions = rpi_config.get("function", {})
    if not isinstance(functions, dict):
        raise RpiConfigError("function config must be an object")

    function_config = functions.get(function_code)
    if not isinstance(function_config, dict):
        raise RpiConfigError(f"Unsupported product function code: {function_code}")

    jobs = function_config.get("jobs", [])
    if not isinstance(jobs, list) or not all(isinstance(item, str) for item in jobs):
        raise RpiConfigError(
            f"function.{function_code}.jobs must be a list of job names"
        )

    return jobs


class GpioController:
    def __init__(self, gpio_config: dict[int, dict[str, Any]]) -> None:
        self._gpio_config = gpio_config
        self._pigpio: Any | None = None
        self._pi: Any | None = None
        self.simulated = True

        app_config = load_config()

        try:
            import pigpio  # pylint: disable=import-outside-toplevel
        except ImportError as e:
            if app_config.simulate_gpio:
                return
            raise e

        pi = pigpio.pi(show_errors=False)
        if pi.connected:
            self._pigpio = pigpio
            self._pi = pi
            self.simulated = False
        elif app_config.simulate_gpio:
            pi.stop()
        else:
            raise RpiConfigError("Failed to connect to pigpio daemon")

    def setup_all(self) -> None:
        for pin, config in self._gpio_config.items():
            mode = str(config.get("mode", "output")).lower()
            state = str(config.get("state", "high"))

            if mode != "output":
                raise RpiConfigError(f"GPIO {pin} must be configured as output")

            value = _state_value(state)
            if self._pi is not None and self._pigpio is not None:
                self._pi.set_mode(pin, self._pigpio.OUTPUT)
                self._pi.write(pin, value)

    def write(self, pin: int, state: str) -> None:
        value = _state_value(state)

        if self._pi is not None:
            self._pi.write(pin, value)

    def close(self) -> None:
        if self._pi is not None:
            self._pi.stop()


class GpioService:
    def __init__(self, gpio_config: dict[int, dict[str, Any]]) -> None:
        self._gpio_config = gpio_config
        self._controller = GpioController(gpio_config)
        self._lock = threading.Lock()

        try:
            self._controller.setup_all()
        except Exception:
            self._controller.close()
            raise

    @property
    def simulated(self) -> bool:
        return self._controller.simulated

    def execute_job(self, job_name: str, job_config: dict[str, Any]) -> TouchResult:
        uses = _parse_job_uses(job_config, self._gpio_config)
        actions = _parse_job_actions(job_config, uses)

        steps: list[dict[str, Any]] = []
        with self._lock:
            try:
                for item in actions:
                    steps.append(self._execute_action(item, uses))
            finally:
                self._reset_uses(uses)

        return TouchResult(
            command=_command_name(job_name),
            simulated=self.simulated,
            steps=steps,
        )

    def _execute_action(
        self, action: dict[str, Any], uses: dict[str, GpioUse]
    ) -> dict[str, Any]:
        key = action["use"]
        value = action["set"]
        use = uses[key]

        if use.type == ResourceType.GPIO and use.mode == "output":
            value = str(value).lower()
            self._controller.write(use.pin, value)
        elif use.type == ResourceType.TIME:
            value = float(value or 0)
            time.sleep(value)

        return {key: value}

    def _reset_uses(self, uses: dict[str, GpioUse]):
        for use in uses.values():
            if (
                use.type == ResourceType.GPIO
                and use.mode == ResourceMode.OUTPUT
                and use.final == ResourceState.RESET
            ):
                self._controller.write(use.pin, use.state)

    def close(self) -> None:
        self._controller.close()


def initialize_gpio_service(path: Path = APP_CONFIG_PATH) -> GpioService:
    global _GPIO_SERVICE

    with _GPIO_SERVICE_LOCK:
        if _GPIO_SERVICE is not None:
            return _GPIO_SERVICE

        rpi_config = _read_rpi_config(path)
        gpio_config = _normalize_gpio_config(rpi_config.get("GPIO", {}))
        _GPIO_SERVICE = GpioService(gpio_config)

        return _GPIO_SERVICE


def shutdown_gpio_service() -> None:
    global _GPIO_SERVICE

    with _GPIO_SERVICE_LOCK:
        if _GPIO_SERVICE is None:
            return

        _GPIO_SERVICE.close()
        _GPIO_SERVICE = None


def _gpio_service() -> GpioService:
    return initialize_gpio_service()


def execute_rpi_job(job_name: str) -> TouchResult:
    rpi_config = _read_rpi_config()
    return _gpio_service().execute_job(job_name, _job_config(rpi_config, job_name))


def execute_function(function_code: str) -> list[TouchResult]:
    rpi_config = _read_rpi_config()
    return [
        execute_rpi_job(job_name)
        for job_name in _function_jobs(rpi_config, function_code)
    ]


def configured_function_codes() -> list[str]:
    functions = _read_rpi_config().get("function", {})
    if not isinstance(functions, dict):
        raise RpiConfigError("function config must be an object")

    return [str(function_code) for function_code in functions.keys()]


def product_code() -> str:
    return str(_read_rpi_config().get("product_code", ""))


def execute_touch() -> TouchResult:
    return execute_rpi_job("touch")
