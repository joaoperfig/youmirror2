"""Continuous-rotation servo control through the Waveshare Servo HAT.

The HAT uses a PCA9685.  A control value is a 12-bit PWM pulse tick at 50 Hz:
the calibrated stopped value holds still, and values either side rotate in
opposite directions.  Do not command past the physical travel limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from project_config import load_config


Speed = Literal["fast_positive", "slow_positive", "stopped", "slow_negative", "fast_negative"]


@dataclass(frozen=True)
class ServoSettings:
    channel: int
    fast_positive_speed: int
    slow_positive_speed: int
    stopped_speed: int
    slow_negative_speed: int
    fast_negative_speed: int

    def value_for(self, speed: Speed) -> int:
        return int(getattr(self, f"{speed}_speed"))


class ServoController:
    """Control pan (channel 0) and tilt (channel 1) independently."""

    def __init__(self) -> None:
        config = load_config()["servos"]
        self.pan = ServoSettings(**config["pan"])
        self.tilt = ServoSettings(**config["tilt"])
        self._frequency = int(config["pwm_frequency_hz"])
        self._driver = None

    def start(self) -> None:
        try:
            import Adafruit_PCA9685
        except ImportError as error:
            raise RuntimeError(
                "The Waveshare Servo HAT requires Adafruit_PCA9685. Install it on the Pi."
            ) from error
        self._driver = Adafruit_PCA9685.PCA9685(address=0x40)
        self._driver.set_pwm_freq(self._frequency)
        self.stop_all()

    def set_speed(self, axis: Literal["pan", "tilt"], speed: Speed) -> None:
        """Set one continuous servo's calibrated speed for this loop iteration."""
        if self._driver is None:
            raise RuntimeError("Servo controller has not been started.")
        settings = self.pan if axis == "pan" else self.tilt
        self._driver.set_pwm(settings.channel, 0, settings.value_for(speed))

    def set_raw(self, axis: Literal["pan", "tilt"], value: int) -> None:
        """Send a calibration pulse value. Intended only for servo_callibrate.py."""
        if self._driver is None:
            raise RuntimeError("Servo controller has not been started.")
        settings = self.pan if axis == "pan" else self.tilt
        self._driver.set_pwm(settings.channel, 0, int(value))

    def stop_all(self) -> None:
        if self._driver is not None:
            self.set_speed("pan", "stopped")
            self.set_speed("tilt", "stopped")

    def close(self) -> None:
        self.stop_all()

    def __enter__(self) -> "ServoController":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
