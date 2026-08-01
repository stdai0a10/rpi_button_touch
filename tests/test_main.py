from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from app import main


class LifespanStateTests(IsolatedAsyncioTestCase):
    async def test_outputs_ready_and_stop_around_service_lifespan(self) -> None:
        events: list[str] = []
        scheduler = object()

        with (
            patch.object(
                main,
                "initialize_gpio_service",
                side_effect=lambda: events.append("initialize_gpio"),
            ),
            patch.object(
                main,
                "start_job_scheduler",
                side_effect=lambda: events.append("start_scheduler") or scheduler,
            ),
            patch.object(
                main,
                "execute_state",
                side_effect=lambda state: events.append(f"state:{state}"),
            ),
            patch.object(
                main,
                "stop_job_scheduler",
                side_effect=lambda value: events.append(
                    "stop_scheduler" if value is scheduler else "wrong_scheduler"
                ),
            ),
            patch.object(
                main,
                "shutdown_gpio_service",
                side_effect=lambda: events.append("shutdown_gpio"),
            ),
        ):
            async with main.lifespan(main.app):
                events.append("serving")

        self.assertEqual(
            events,
            [
                "initialize_gpio",
                "start_scheduler",
                "state:ready",
                "serving",
                "stop_scheduler",
                "state:stop",
                "shutdown_gpio",
            ],
        )

    async def test_startup_failure_still_outputs_stop_and_releases_gpio(self) -> None:
        events: list[str] = []

        with (
            patch.object(main, "initialize_gpio_service"),
            patch.object(main, "start_job_scheduler", side_effect=RuntimeError("boom")),
            patch.object(
                main,
                "execute_state",
                side_effect=lambda state: events.append(f"state:{state}"),
            ),
            patch.object(
                main,
                "stop_job_scheduler",
                side_effect=lambda scheduler: events.append("stop_scheduler"),
            ),
            patch.object(
                main,
                "shutdown_gpio_service",
                side_effect=lambda: events.append("shutdown_gpio"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                async with main.lifespan(main.app):
                    self.fail("The lifespan should not start")

        self.assertEqual(
            events,
            ["stop_scheduler", "state:stop", "shutdown_gpio"],
        )
