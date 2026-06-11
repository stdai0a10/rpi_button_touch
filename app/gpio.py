from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import RPI_CONFIG_PATH


class RpiConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TouchResult:
    command: str
    simulated: bool
    steps: list[dict[str, Any]]


def _read_rpi_config(path: Path = RPI_CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise RpiConfigError(f"{path} must contain a JSON object")

    return data


def _gpio_number(label: str) -> int:
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


class GpioController:
    def __init__(self, gpio_config: dict[str, Any]) -> None:
        self._gpio_config = gpio_config
        self._pigpio: Any | None = None
        self._pi: Any | None = None
        self.simulated = True

        try:
            import pigpio
        except ImportError:
            return

        pi = pigpio.pi(show_errors=False)
        if not pi.connected:
            pi.stop()
            return

        self._pigpio = pigpio
        self._pi = pi
        self.simulated = False

    def setup(self, labels: list[str]) -> None:
        for label in labels:
            config = self._gpio_config.get(label, {})
            mode = str(config.get("mode", "output")).lower()
            state = str(config.get("state", "high"))

            if mode != "output":
                raise RpiConfigError(f"{label} must be configured as output")

            gpio = _gpio_number(label)
            if self._pi is not None and self._pigpio is not None:
                self._pi.set_mode(gpio, self._pigpio.OUTPUT)
                self._pi.write(gpio, _state_value(state))

    def write(self, label: str, state: str) -> None:
        gpio = _gpio_number(label)
        value = _state_value(state)

        if self._pi is not None:
            self._pi.write(gpio, value)

    def close(self) -> None:
        if self._pi is not None:
            self._pi.stop()


def execute_touch() -> TouchResult:
    rpi_config = _read_rpi_config()
    gpio_config = rpi_config.get("GPIO", {})
    touch_config = rpi_config.get("job", {}).get("touch", {})

    if not isinstance(gpio_config, dict):
        raise RpiConfigError("GPIO config must be an object")
    if not isinstance(touch_config, dict):
        raise RpiConfigError("job.touch config must be an object")

    uses = touch_config.get("uses", [])
    action = touch_config.get("action", [])
    if not isinstance(uses, list) or not all(isinstance(item, str) for item in uses):
        raise RpiConfigError("job.touch.uses must be a list of GPIO labels")
    if not isinstance(action, list) or not all(isinstance(item, dict) for item in action):
        raise RpiConfigError("job.touch.action must be a list of action objects")

    controller = GpioController(gpio_config)
    steps: list[dict[str, Any]] = []

    try:
        controller.setup(uses)

        for item in action:
            for key, value in item.items():
                if key == "wait":
                    seconds = float(value)
                    time.sleep(seconds)
                    steps.append({"wait": seconds})
                    continue

                state = str(value)
                controller.write(key, state)
                steps.append({key: state.lower()})
    finally:
        controller.close()

    return TouchResult(command="Touch", simulated=controller.simulated, steps=steps)
