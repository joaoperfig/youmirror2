"""Fail-safe continuous-servo control through a PCA9685 Servo HAT."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Literal, cast

from project_config import load_config, validate_config


Speed = Literal["fast_positive", "slow_positive", "stopped", "slow_negative", "fast_negative"]
Axis = Literal["pan", "tilt"]


@dataclass(frozen=True)
class ServoSettings:
    channel: int
    inverted: bool
    direction_confirmed: bool
    fast_positive_us: int
    slow_positive_us: int
    stopped_us: int
    slow_negative_us: int
    fast_negative_us: int

    def value_for(self, speed: Speed) -> int:
        return int(getattr(self, f"{speed}_us"))


@dataclass
class _MotionState:
    direction: int = 0
    direction_started: float = 0.0
    neutral_started: float = 0.0
    locked_direction: int = 0


class ServoController:
    """Control both axes with a lease watchdog and continuous-motion budget."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        driver_factory: Callable[[int, int], Any] | None = None,
    ) -> None:
        full_config = config if config is not None else load_config()
        validate_config(full_config)
        servo_config = full_config["servos"]
        self.pan = ServoSettings(**servo_config["pan"])
        self.tilt = ServoSettings(**servo_config["tilt"])
        self._frequency = int(servo_config["pwm_frequency_hz"])
        self._address = int(servo_config["i2c_address"])
        self._safe_min_us = int(servo_config["safe_min_us"])
        self._safe_max_us = int(servo_config["safe_max_us"])
        self._lease = float(servo_config["movement_lease_s"])
        self._max_motion = float(servo_config["max_continuous_motion_s"])
        self._cooldown = float(servo_config["motion_cooldown_s"])
        self._driver_factory = driver_factory
        self._driver: Any = None
        self._i2c: Any = None
        self._lock = threading.RLock()
        self._watchdog_stop = threading.Event()
        self._watchdog: threading.Thread | None = None
        self._watchdog_error: Exception | None = None
        self._lease_deadline = 0.0
        now = time.monotonic()
        self._motion = {
            "pan": _MotionState(neutral_started=now),
            "tilt": _MotionState(neutral_started=now),
        }

    def start(self) -> None:
        with self._lock:
            if self._driver is not None:
                raise RuntimeError("Servo controller is already started.")
        driver = None
        i2c = None
        try:
            if self._driver_factory is not None:
                driver = self._driver_factory(self._address, self._frequency)
            else:
                try:
                    import board
                    import busio
                    from adafruit_pca9685 import PCA9685
                except ImportError as error:
                    raise RuntimeError(
                        "Install adafruit-circuitpython-pca9685 and Adafruit-Blinka."
                    ) from error
                i2c = busio.I2C(board.SCL, board.SDA)
                driver = PCA9685(i2c, address=self._address)
                driver.frequency = self._frequency
            with self._lock:
                self._driver = driver
                self._i2c = i2c
                self._write_neutral_locked("pan")
                self._write_neutral_locked("tilt")
                self._lease_deadline = 0.0
        except Exception:
            if driver is not None and hasattr(driver, "channels"):
                for axis in ("pan", "tilt"):
                    try:
                        driver.channels[
                            self._settings(cast(Axis, axis)).channel
                        ].duty_cycle = 0
                    except Exception:
                        pass
            try:
                self._cleanup_backend(driver, i2c)
            except Exception:
                pass
            with self._lock:
                self._driver = None
                self._i2c = None
            raise
        self._watchdog_stop.clear()
        self._watchdog_error = None
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, name="servo-watchdog", daemon=True
        )
        self._watchdog.start()

    def set_speed(self, axis: Axis, speed: Speed) -> bool:
        """Set one axis and refresh the lease. Return False if motion is locked out."""
        self._validate_axis(axis)
        current = {"pan": "stopped", "tilt": "stopped"}
        current[axis] = speed
        allowed = self.set_speeds(
            cast(Speed, current["pan"]), cast(Speed, current["tilt"])
        )
        return allowed[0 if axis == "pan" else 1]

    def set_speeds(self, pan: Speed, tilt: Speed) -> tuple[bool, bool]:
        """Atomically apply a complete tracking decision and refresh its lease."""
        now = time.monotonic()
        with self._lock:
            self._require_started()
            pan_allowed = self._apply_speed_locked("pan", pan, now)
            tilt_allowed = self._apply_speed_locked("tilt", tilt, now)
            self._lease_deadline = now + self._lease if pan != "stopped" or tilt != "stopped" else 0.0
            return pan_allowed, tilt_allowed

    def set_raw_us(self, axis: Axis, pulse_us: int) -> None:
        """Send one already-validated calibration pulse."""
        self._validate_axis(axis)
        self._validate_pulse(pulse_us)
        with self._lock:
            self._require_started()
            self._write_pulse_locked(axis, pulse_us)
            self._lease_deadline = time.monotonic() + self._lease

    def set_neutral(self, axis: Axis, pulse_us: int) -> None:
        """Immediately make an accepted calibration neutral active in memory."""
        self._validate_axis(axis)
        self._validate_pulse(pulse_us)
        attribute = axis
        settings = self._settings(axis)
        setattr(self, attribute, replace(settings, stopped_us=int(pulse_us)))
        with self._lock:
            if self._driver is not None:
                self._write_neutral_locked(axis)

    def stop_all(self) -> None:
        errors: list[Exception] = []
        with self._lock:
            if self._driver is None:
                return
            for axis in ("pan", "tilt"):
                try:
                    self._write_neutral_locked(cast(Axis, axis))
                    self._record_neutral(cast(Axis, axis), time.monotonic())
                except Exception as error:
                    errors.append(error)
            self._lease_deadline = 0.0
        if errors:
            raise RuntimeError("Failed to stop one or more servos.") from errors[0]

    def close(self) -> None:
        self._watchdog_stop.set()
        watchdog = self._watchdog
        if watchdog is not None and watchdog is not threading.current_thread():
            watchdog.join(timeout=max(self._lease * 2, 0.5))
        self._watchdog = None
        with self._lock:
            driver, i2c = self._driver, self._i2c
            self._driver = None
            self._i2c = None
        if driver is None:
            return
        first_error: Exception | None = None
        for axis in ("pan", "tilt"):
            try:
                settings = self._settings(cast(Axis, axis))
                self._write_driver_pulse(driver, settings.channel, settings.stopped_us)
            except Exception as error:
                first_error = first_error or error
        time.sleep(0.05)
        for axis in ("pan", "tilt"):
            try:
                driver.channels[self._settings(cast(Axis, axis)).channel].duty_cycle = 0
            except Exception as error:
                first_error = first_error or error
        try:
            self._cleanup_backend(driver, i2c)
        except Exception as error:
            first_error = first_error or error
        if first_error is not None:
            raise RuntimeError("Servo shutdown was incomplete.") from first_error

    def _apply_speed_locked(self, axis: Axis, speed: Speed, now: float) -> bool:
        direction = 0 if speed == "stopped" else (1 if speed.endswith("positive") else -1)
        state = self._motion[axis]
        if direction == 0:
            self._record_neutral(axis, now)
            self._write_neutral_locked(axis)
            return True
        if state.locked_direction:
            if direction == -state.locked_direction:
                state.locked_direction = 0
                state.direction = direction
                state.direction_started = now
            elif now - state.neutral_started >= self._cooldown:
                state.locked_direction = 0
                state.direction = direction
                state.direction_started = now
            else:
                self._write_neutral_locked(axis)
                return False
        elif direction != state.direction:
            state.direction = direction
            state.direction_started = now
        if now - state.direction_started >= self._max_motion:
            state.locked_direction = direction
            state.neutral_started = now
            state.direction = 0
            self._write_neutral_locked(axis)
            return False
        self._write_pulse_locked(axis, self._settings(axis).value_for(speed))
        return True

    def _record_neutral(self, axis: Axis, now: float) -> None:
        state = self._motion[axis]
        if state.direction != 0:
            state.neutral_started = now
        state.direction = 0

    def _watchdog_loop(self) -> None:
        while not self._watchdog_stop.wait(min(self._lease / 4, 0.05)):
            with self._lock:
                if (
                    self._driver is not None
                    and self._lease_deadline
                    and time.monotonic() >= self._lease_deadline
                ):
                    first_error: Exception | None = None
                    for axis in ("pan", "tilt"):
                        try:
                            typed_axis = cast(Axis, axis)
                            self._write_neutral_locked(typed_axis)
                            self._record_neutral(typed_axis, time.monotonic())
                        except Exception as error:
                            first_error = first_error or error
                    if first_error is not None and self._watchdog_error is None:
                        self._watchdog_error = RuntimeError(
                            "Watchdog could not stop one or more servos."
                        )
                    self._lease_deadline = 0.0

    def _write_neutral_locked(self, axis: Axis) -> None:
        settings = self._settings(axis)
        self._write_pulse_locked(axis, settings.stopped_us)

    def _write_pulse_locked(self, axis: Axis, pulse_us: int) -> None:
        self._require_started()
        settings = self._settings(axis)
        self._write_driver_pulse(self._driver, settings.channel, pulse_us)

    def _write_driver_pulse(self, driver: Any, channel: int, pulse_us: int) -> None:
        duty_cycle = round(pulse_us * self._frequency * 65535 / 1_000_000)
        driver.channels[channel].duty_cycle = max(0, min(0xFFFF, duty_cycle))

    @staticmethod
    def _cleanup_backend(driver: Any, i2c: Any) -> None:
        first_error: Exception | None = None
        if driver is not None and hasattr(driver, "deinit"):
            try:
                driver.deinit()
            except Exception as error:
                first_error = error
        if i2c is not None and hasattr(i2c, "deinit"):
            try:
                i2c.deinit()
            except Exception as error:
                first_error = first_error or error
        if first_error is not None:
            raise first_error

    def _settings(self, axis: Axis) -> ServoSettings:
        return self.pan if axis == "pan" else self.tilt

    def _require_started(self) -> None:
        if self._driver is None:
            raise RuntimeError("Servo controller has not been started.")
        if self._watchdog_error is not None:
            raise self._watchdog_error

    @staticmethod
    def _validate_axis(axis: str) -> None:
        if axis not in ("pan", "tilt"):
            raise ValueError(f"Unknown servo axis: {axis}")

    def _validate_pulse(self, pulse_us: int) -> None:
        if type(pulse_us) is not int or not self._safe_min_us <= pulse_us <= self._safe_max_us:
            raise ValueError(
                f"Pulse must be {self._safe_min_us}..{self._safe_max_us} microseconds."
            )

    def __enter__(self) -> "ServoController":
        self.start()
        return self

    def __exit__(self, exception_type: object, *_: object) -> None:
        if exception_type is None:
            self.close()
            return
        try:
            self.close()
        except Exception:
            pass
