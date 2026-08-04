"""Terminal/SSH keyboard test for the pan and tilt continuous servos."""

from __future__ import annotations

import os
import signal
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
    if not sys.stdin.isatty():
        raise RuntimeError("servo_test.py requires an interactive terminal.")
    if os.name == "nt":
        import msvcrt

        return msvcrt.getwch()
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        key = sys.stdin.read(1)
        if key == "":
            raise EOFError("Terminal disconnected.")
        return key
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _request_stop(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main() -> None:
    print("w/a/s/d: slow, W/A/S/D: fast; q: quit.")
    for signal_name in ("SIGTERM", "SIGHUP"):
        shutdown_signal = getattr(signal, signal_name, None)
        if shutdown_signal is not None:
            signal.signal(shutdown_signal, _request_stop)
    try:
        with ServoController() as servos:
            while True:
                key = read_key()
                if key in ("\x03", "\x04") or key.lower() == "q":
                    break
                command = KEYS.get(key)
                if command is None:
                    continue
                axis, speed = command
                try:
                    servos.set_speed(axis, speed)
                    # Terminals report presses but not releases, so each key
                    # produces one bounded movement pulse.
                    time.sleep(0.08)
                finally:
                    servos.stop_all()
    except (KeyboardInterrupt, EOFError):
        pass
    print("\nServos stopped.")


if __name__ == "__main__":
    main()
