from unittest import TestCase
from unittest.mock import Mock, call, patch

from app import gpio


class ExecuteServiceStateTests(TestCase):
    def test_state_actions_write_the_configured_gpio_values(self) -> None:
        controller = Mock()
        controller.simulated = True
        ready = {
            "uses": [
                {
                    "name": "GPIO 14",
                    "type": "GPIO",
                    "value": 14,
                    "final": "keep",
                }
            ],
            "action": [{"GPIO 14": "high"}],
        }
        stop = {
            "uses": ready["uses"],
            "action": [{"GPIO 14": "low"}],
        }

        with patch.object(gpio, "GpioController", return_value=controller):
            service = gpio.GpioService(
                {14: {"mode": "output", "state": "low"}}
            )

        service.execute_job("ready", ready)
        service.execute_job("stop", stop)

        self.assertEqual(
            controller.write.call_args_list,
            [call(14, "high"), call(14, "low")],
        )

    def test_executes_configured_state_as_gpio_job(self) -> None:
        state_config = {
            "uses": [
                {
                    "name": "GPIO 14",
                    "type": "GPIO",
                    "value": 14,
                    "final": "keep",
                }
            ],
            "action": [{"GPIO 14": "high"}],
        }
        service = Mock(spec=gpio.GpioService)
        expected = gpio.TouchResult(
            command="Ready",
            simulated=True,
            steps=[{"GPIO 14": "high"}],
        )
        service.execute_job.return_value = expected

        with (
            patch.object(
                gpio,
                "_read_rpi_config",
                return_value={"state": {"ready": state_config}},
            ),
            patch.object(gpio, "_gpio_service", return_value=service),
        ):
            result = gpio.execute_state("ready")

        self.assertEqual(result, expected)
        service.execute_job.assert_called_once_with("ready", state_config)

    def test_missing_state_config_is_a_no_op(self) -> None:
        with (
            patch.object(gpio, "_read_rpi_config", return_value={}),
            patch.object(gpio, "_gpio_service") as gpio_service,
        ):
            result = gpio.execute_state("ready")

        self.assertIsNone(result)
        gpio_service.assert_not_called()

    def test_invalid_state_config_is_rejected(self) -> None:
        with patch.object(gpio, "_read_rpi_config", return_value={"state": []}):
            with self.assertRaisesRegex(
                gpio.RpiConfigError, "state config must be an object"
            ):
                gpio.execute_state("ready")
