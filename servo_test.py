"""Terminal/SSH keyboard test for the pan and tilt continuous servos."""

from __future__ import annotations

import os
import sys
import time

from servo_control import ServoController


KEYS = {
    "w": ("tilt", "slow_positive"),
    "s": ("tilt", "slow_negative"),
    "a": ("pan", "slow_negative"),
    "d": ("pan", "slow_positive"),
    "W": ("tilt", "fast_positive"),
    "S": ("tilt", "fast_negative"),
    "A": ("pan", "fast_negative"),
    "D": ("pan", "fast_positive"),
}


def read_key() -> str:
    """Read one key immediately; raw terminal mode also works through SSH."""
    if os.name == "nt":
        import msvcrt

        return msvcrt.getwch()
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def main() -> None:
    print("w/a/s/d: slow, W/A/S/D: fast; q: quit.")
    try:
        with ServoController() as servos:
            while True:
                key = read_key()
                if key.lower() == "q":
                    break
                command = KEYS.get(key)
                if command is None:
                    continue
                axis, speed = command
                servos.set_speed(axis, speed)
                # Terminal input reports presses but not releases.  A short
                # pulse makes repeated keypresses feel like held movement and
                # ensures the servo stops if an SSH session disconnects.
                time.sleep(0.08)
                servos.set_speed(axis, "stopped")
    except KeyboardInterrupt:
        pass
    print("\nServos stopped.")


if __name__ == "__main__":
    main()
