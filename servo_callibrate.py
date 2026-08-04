"""Safely calibrate continuous-servo pulse widths in microseconds."""

from __future__ import annotations

import time

from project_config import load_config, save_config
from servo_control import ServoController


SPEEDS = (
    "slow_positive_us",
    "slow_negative_us",
    "fast_positive_us",
    "fast_negative_us",
)
TEST_PULSE_S = 0.15


def calibrate_axis(servos: ServoController, config: dict, axis: str) -> None:
    servo_config = config["servos"]
    axis_config = servo_config[axis]
    minimum = servo_config["safe_min_us"]
    maximum = servo_config["safe_max_us"]
    print(f"\nCalibrating {axis} (channel {axis_config['channel']}).")
    current_neutral = axis_config["stopped_us"]
    while True:
        value = _read_pulse(
            "stopped_us",
            current_neutral,
            axis_config["slow_negative_us"],
            axis_config["slow_positive_us"],
        )
        servos.set_neutral(axis, value)
        time.sleep(TEST_PULSE_S)
        if input("Is the servo reliably stopped? [y/N]: ").strip().lower() == "y":
            axis_config["stopped_us"] = value
            save_config(config)
            print("Neutral saved immediately.")
            break
        servos.set_neutral(axis, current_neutral)
        print("Neutral rejected; try another value.")

    for name in SPEEDS:
        current = axis_config[name]
        lower, upper = {
            "slow_positive_us": (axis_config["stopped_us"], axis_config["fast_positive_us"]),
            "slow_negative_us": (axis_config["fast_negative_us"], axis_config["stopped_us"]),
            "fast_positive_us": (axis_config["slow_positive_us"], maximum),
            "fast_negative_us": (minimum, axis_config["slow_negative_us"]),
        }[name]
        value = _read_pulse(name, current, lower, upper)
        try:
            servos.set_raw_us(axis, value)
            time.sleep(TEST_PULSE_S)
        finally:
            servos.set_speed(axis, "stopped")
        if input("Accept this brief movement? [y/N]: ").strip().lower() == "y":
            axis_config[name] = value
        else:
            print("Value rejected; keeping the previous setting.")
    response = input(
        f"Invert {axis} tracking direction? "
        f"[{'Y/n' if axis_config['inverted'] else 'y/N'}]: "
    ).strip().lower()
    if response in ("y", "n"):
        axis_config["inverted"] = response == "y"
    axis_config["direction_confirmed"] = True
    save_config(config)


def _read_pulse(name: str, current: int, minimum: int, maximum: int) -> int:
    while True:
        response = input(
            f"{name} [{current} us] ({minimum}..{maximum}, Enter keeps, q quits): "
        ).strip()
        if response.lower() == "q":
            raise KeyboardInterrupt
        try:
            value = current if not response else int(response)
        except ValueError:
            print("Enter a whole number of microseconds.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"Pulse width must be between {minimum} and {maximum} microseconds.")


def main() -> None:
    print(
        "Neutral is calibrated first. Directional tests automatically stop after "
        f"{TEST_PULSE_S:.2f} seconds."
    )
    config = load_config()
    try:
        with ServoController(config) as servos:
            calibrate_axis(servos, config, "pan")
            calibrate_axis(servos, config, "tilt")
    except KeyboardInterrupt:
        print("\nCalibration cancelled; previously confirmed neutral values remain saved.")
        return
    print("Servo calibration saved.")


if __name__ == "__main__":
    main()
