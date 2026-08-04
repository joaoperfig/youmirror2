"""Hardware-free regression tests for configuration and fail-safe control."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import project_config
from camera_control import Face, FaceTracker
from main import speed_for_offset
from servo_control import ServoController


class FakeChannel:
    def __init__(self) -> None:
        self.duty_cycle = 0


class FakeDriver:
    def __init__(self) -> None:
        self.channels = [FakeChannel() for _ in range(16)]
        self.deinitialized = False

    def deinit(self) -> None:
        self.deinitialized = True


class FailingChannel(FakeChannel):
    @property
    def duty_cycle(self) -> int:
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, value: int) -> None:
        if getattr(self, "fail", False):
            raise OSError("simulated I2C failure")
        self._duty_cycle = value


class ConfigurationTests(unittest.TestCase):
    def test_legacy_ticks_are_migrated_to_microseconds(self) -> None:
        legacy = {
            "camera": {"true_center": [320, 240]},
            "servos": {
                "pwm_frequency_hz": 50,
                "pan": {"stopped_speed": 307},
                "tilt": {"stopped_speed": 307},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "mirror_config.json")
            path.write_text(json.dumps(legacy), encoding="utf-8")
            with patch.object(project_config, "CONFIG_PATH", path):
                config = project_config.load_config()
        self.assertEqual(config["servos"]["pan"]["stopped_us"], 1499)
        self.assertEqual(config["camera"]["true_center"]["position"], [320, 240])

    def test_duplicate_channels_are_rejected(self) -> None:
        config = deepcopy(project_config.DEFAULT_CONFIG)
        config["servos"]["tilt"]["channel"] = 0
        with self.assertRaisesRegex(RuntimeError, "different"):
            project_config.validate_config(config)

    def test_unknown_keys_are_rejected(self) -> None:
        config = deepcopy(project_config.DEFAULT_CONFIG)
        config["servos"]["surprise"] = True
        with self.assertRaisesRegex(RuntimeError, "unknown"):
            project_config.validate_config(config)


class ServoSafetyTests(unittest.TestCase):
    def make_controller(self) -> tuple[ServoController, FakeDriver]:
        config = deepcopy(project_config.DEFAULT_CONFIG)
        config["servos"]["movement_lease_s"] = 0.05
        config["servos"]["max_continuous_motion_s"] = 0.1
        config["servos"]["motion_cooldown_s"] = 0.1
        driver = FakeDriver()
        controller = ServoController(config, driver_factory=lambda _address, _frequency: driver)
        controller.start()
        return controller, driver

    def test_microseconds_are_converted_to_duty_cycle(self) -> None:
        controller, driver = self.make_controller()
        try:
            controller.set_raw_us("pan", 1500)
            self.assertEqual(driver.channels[0].duty_cycle, round(1500 * 50 * 65535 / 1_000_000))
        finally:
            controller.close()

    def test_watchdog_returns_moving_axes_to_neutral(self) -> None:
        controller, driver = self.make_controller()
        try:
            controller.set_speeds("slow_positive", "slow_negative")
            time.sleep(0.12)
            neutral = round(1499 * 50 * 65535 / 1_000_000)
            self.assertEqual(driver.channels[0].duty_cycle, neutral)
            self.assertEqual(driver.channels[1].duty_cycle, neutral)
        finally:
            controller.close()

    def test_continuous_motion_is_temporarily_locked_out(self) -> None:
        controller, _driver = self.make_controller()
        try:
            result = (True, True)
            for _ in range(4):
                result = controller.set_speeds("slow_positive", "stopped")
                time.sleep(0.035)
            self.assertEqual(result, (False, True))
            self.assertEqual(controller.set_speeds("slow_negative", "stopped"), (True, True))
        finally:
            controller.close()

    def test_invalid_axis_is_not_treated_as_tilt(self) -> None:
        controller, _driver = self.make_controller()
        try:
            with self.assertRaises(ValueError):
                controller.set_speed("roll", "stopped")  # type: ignore[arg-type]
        finally:
            controller.close()

    def test_partial_startup_deinitializes_driver(self) -> None:
        config = deepcopy(project_config.DEFAULT_CONFIG)
        driver = FakeDriver()
        failing = FailingChannel()
        failing.fail = True
        driver.channels[1] = failing
        controller = ServoController(
            config, driver_factory=lambda _address, _frequency: driver
        )
        with self.assertRaises(OSError):
            controller.start()
        self.assertTrue(driver.deinitialized)

    def test_stop_attempts_tilt_after_pan_write_fails(self) -> None:
        controller, driver = self.make_controller()
        pan = FailingChannel()
        pan.fail = True
        driver.channels[0] = pan
        driver.channels[1].duty_cycle = 1
        try:
            with self.assertRaises(RuntimeError):
                controller.stop_all()
            neutral = round(1499 * 50 * 65535 / 1_000_000)
            self.assertEqual(driver.channels[1].duty_cycle, neutral)
        finally:
            pan.fail = False
            controller.close()


class TrackingTests(unittest.TestCase):
    def test_speed_boundaries_and_inversion(self) -> None:
        self.assertEqual(speed_for_offset(15, 100), "stopped")
        self.assertEqual(speed_for_offset(16, 100), "slow_positive")
        self.assertEqual(speed_for_offset(30, 100), "fast_positive")
        self.assertEqual(speed_for_offset(30, 100, inverted=True), "fast_negative")

    def test_tracker_rejects_implausible_target_jump(self) -> None:
        tracker = FaceTracker(max_jump_fraction=0.2)
        first = tracker.update([Face(10, 10, 40, 40)], (640, 480), 1.0)
        jumped = tracker.update([Face(500, 300, 40, 40)], (640, 480), 1.1)
        self.assertIsNotNone(first)
        self.assertIsNone(jumped)

    def test_tracker_smooths_nearby_target(self) -> None:
        tracker = FaceTracker(smoothing=0.5)
        tracker.update([Face(100, 100, 40, 40)], (640, 480), 1.0)
        smoothed = tracker.update([Face(120, 100, 40, 40)], (640, 480), 1.1)
        self.assertEqual(smoothed, Face(110, 100, 40, 40))


if __name__ == "__main__":
    unittest.main()
