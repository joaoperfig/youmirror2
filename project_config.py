"""Persistent calibration values shared by the mirror control scripts.

The camera is fixed to the mirror, so the saved camera center is the one
pixel position that physically centers a person's reflection.  Servo values
are PCA9685 pulse ticks at 50 Hz, not positional angles: both servos are
continuous-rotation motors.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).with_name("mirror_config.json")

# These are intentionally conservative starting values.  Calibration replaces
# them for the particular servos and their mechanical mounting.
DEFAULT_CONFIG: dict[str, Any] = {
    "camera": {"true_center": None},
    "servos": {
        "pwm_frequency_hz": 50,
        "pan": {
            "channel": 0,
            "fast_positive_speed": 360,
            "slow_positive_speed": 325,
            "stopped_speed": 307,
            "slow_negative_speed": 290,
            "fast_negative_speed": 255,
        },
        "tilt": {
            "channel": 1,
            "fast_positive_speed": 360,
            "slow_positive_speed": 325,
            "stopped_speed": 307,
            "slow_negative_speed": 290,
            "fast_negative_speed": 255,
        },
    },
}


def load_config() -> dict[str, Any]:
    """Load saved values, using defaults for a first run or missing keys."""
    config = deepcopy(DEFAULT_CONFIG)
    if not CONFIG_PATH.exists():
        return config
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read calibration file {CONFIG_PATH}: {error}") from error
    _merge(config, saved)
    return config


def save_config(config: dict[str, Any]) -> None:
    """Atomically save calibration so an interrupted write cannot corrupt it."""
    temporary_path = CONFIG_PATH.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_path, CONFIG_PATH)


def _merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
