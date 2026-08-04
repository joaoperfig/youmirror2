"""Interactively calibrate each continuous servo's five PWM control values."""

from __future__ import annotations

from project_config import load_config, save_config
from servo_control import ServoController


SPEEDS = (
    "fast_positive_speed",
    "slow_positive_speed",
    "stopped_speed",
    "slow_negative_speed",
    "fast_negative_speed",
)


def calibrate_axis(servos: ServoController, config: dict, axis: str) -> None:
    print(f"\nCalibrating {axis} (channel {config['servos'][axis]['channel']}).")
    for name in SPEEDS:
        current = config["servos"][axis][name]
        while True:
            response = input(f"{name} tick value [{current}] (Enter keeps, q quits): ").strip()
            if response.lower() == "q":
                raise KeyboardInterrupt
            value = current if not response else int(response)
            if not 0 <= value <= 4095:
                print("A PCA9685 tick value must be between 0 and 4095.")
                continue
            servos.set_raw(axis, value)
            input("Observe movement, then press Enter to stop and accept this value. ")
            servos.set_speed(axis, "stopped")
            config["servos"][axis][name] = value
            break


def main() -> None:
    print(
        "Set a stopped value first if needed. Use only brief observations: "
        "servo movement is mechanically limited."
    )
    config = load_config()
    try:
        with ServoController() as servos:
            calibrate_axis(servos, config, "pan")
            calibrate_axis(servos, config, "tilt")
    except (KeyboardInterrupt, ValueError):
        print("\nCalibration cancelled; no changes saved.")
        return
    save_config(config)
    print("Servo calibration saved.")


if __name__ == "__main__":
    main()
