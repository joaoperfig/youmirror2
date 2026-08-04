"""Versioned, validated calibration shared by all mirror control scripts."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).with_name("mirror_config.json")
SCHEMA_VERSION = 2
SPEED_KEYS = (
    "fast_positive_us",
    "slow_positive_us",
    "stopped_us",
    "slow_negative_us",
    "fast_negative_us",
)

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "camera": {
        "size": [640, 480],
        "format": "RGB888",
        "hflip": False,
        "vflip": False,
        "true_center": None,
    },
    "servos": {
        "i2c_address": 0x40,
        "pwm_frequency_hz": 50,
        "safe_min_us": 1000,
        "safe_max_us": 2000,
        "movement_lease_s": 0.20,
        "max_continuous_motion_s": 2.0,
        "motion_cooldown_s": 0.50,
        "pan": {
            "channel": 0,
            "inverted": False,
            "direction_confirmed": False,
            "fast_positive_us": 1758,
            "slow_positive_us": 1587,
            "stopped_us": 1499,
            "slow_negative_us": 1416,
            "fast_negative_us": 1245,
        },
        "tilt": {
            "channel": 1,
            "inverted": True,
            "direction_confirmed": False,
            "fast_positive_us": 1758,
            "slow_positive_us": 1587,
            "stopped_us": 1499,
            "slow_negative_us": 1416,
            "fast_negative_us": 1245,
        },
    },
}


def load_config() -> dict[str, Any]:
    """Load, migrate, and validate saved calibration."""
    config = deepcopy(DEFAULT_CONFIG)
    if not CONFIG_PATH.exists():
        validate_config(config)
        return config
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read calibration file {CONFIG_PATH}: {error}") from error
    if not isinstance(saved, dict):
        raise RuntimeError(f"Calibration file {CONFIG_PATH} must contain a JSON object.")
    saved_version = saved.get("schema_version")
    if saved_version not in (None, 1, SCHEMA_VERSION):
        raise RuntimeError(f"Unsupported configuration schema {saved_version!r}.")
    if saved_version != SCHEMA_VERSION:
        saved = _migrate_legacy(saved)
    _merge(config, saved)
    validate_config(config)
    return config


def save_config(config: dict[str, Any]) -> None:
    """Validate and atomically save calibration."""
    config["schema_version"] = SCHEMA_VERSION
    validate_config(config)
    temporary_path = CONFIG_PATH.with_suffix(".json.tmp")
    try:
        temporary_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_path, CONFIG_PATH)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if key not in target:
            raise RuntimeError(f"Unknown calibration setting: {key}")
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value


def _migrate_legacy(saved: dict[str, Any]) -> dict[str, Any]:
    """Convert the original 50 Hz tick schema to microseconds."""
    migrated = deepcopy(DEFAULT_CONFIG)
    camera = saved.get("camera")
    if isinstance(camera, dict) and camera.get("true_center") is not None:
        migrated["camera"]["true_center"] = {
            "position": camera["true_center"],
            "size": [640, 480],
            "format": "RGB888",
            "hflip": False,
            "vflip": False,
            "legacy": True,
        }
    servos = saved.get("servos")
    if not isinstance(servos, dict):
        return migrated
    frequency = servos.get("pwm_frequency_hz", 50)
    if type(frequency) is not int or frequency != 50:
        raise RuntimeError("Legacy servo calibration can only be migrated from 50 Hz.")
    for axis in ("pan", "tilt"):
        old_axis = servos.get(axis)
        if not isinstance(old_axis, dict):
            continue
        if "channel" in old_axis:
            migrated["servos"][axis]["channel"] = old_axis["channel"]
        for old_name, new_name in (
            ("fast_positive_speed", "fast_positive_us"),
            ("slow_positive_speed", "slow_positive_us"),
            ("stopped_speed", "stopped_us"),
            ("slow_negative_speed", "slow_negative_us"),
            ("fast_negative_speed", "fast_negative_us"),
        ):
            if old_name in old_axis:
                ticks = old_axis[old_name]
                if type(ticks) is not int or not 0 <= ticks <= 4095:
                    raise RuntimeError(f"Invalid legacy {axis}.{old_name}.")
                migrated["servos"][axis][new_name] = round(
                    ticks * 1_000_000 / (4096 * frequency)
                )
    return migrated


def validate_config(config: dict[str, Any]) -> None:
    """Reject unsafe or malformed values before hardware is opened."""
    _require_exact_keys(config, DEFAULT_CONFIG, "configuration")
    if config["schema_version"] != SCHEMA_VERSION:
        raise RuntimeError(f"Unsupported configuration schema {config['schema_version']!r}.")

    camera = config["camera"]
    size = camera["size"]
    if (
        not isinstance(size, list)
        or len(size) != 2
        or any(type(value) is not int or value <= 0 for value in size)
    ):
        raise RuntimeError("camera.size must be [positive width, positive height].")
    if camera["format"] != "RGB888":
        raise RuntimeError("camera.format must be RGB888 (BGR array order for OpenCV).")
    for key in ("hflip", "vflip"):
        if type(camera[key]) is not bool:
            raise RuntimeError(f"camera.{key} must be a boolean.")
    _validate_center(camera["true_center"], camera)

    servos = config["servos"]
    address = servos["i2c_address"]
    if type(address) is not int or not 0x40 <= address <= 0x7F:
        raise RuntimeError("servos.i2c_address must be between 0x40 and 0x7f.")
    if servos["pwm_frequency_hz"] != 50:
        raise RuntimeError("Continuous analog servo calibration requires 50 Hz PWM.")
    safe_min = servos["safe_min_us"]
    safe_max = servos["safe_max_us"]
    if (
        type(safe_min) is not int
        or type(safe_max) is not int
        or not 500 <= safe_min < safe_max <= 2500
    ):
        raise RuntimeError("Servo safe pulse range must be within 500..2500 microseconds.")
    for key, low, high in (
        ("movement_lease_s", 0.05, 1.0),
        ("max_continuous_motion_s", 0.1, 10.0),
        ("motion_cooldown_s", 0.1, 10.0),
    ):
        value = servos[key]
        if type(value) not in (int, float) or not low <= value <= high:
            raise RuntimeError(f"servos.{key} must be between {low} and {high}.")

    channels: list[int] = []
    for axis in ("pan", "tilt"):
        settings = servos[axis]
        channel = settings["channel"]
        if type(channel) is not int or not 0 <= channel <= 15:
            raise RuntimeError(f"servos.{axis}.channel must be between 0 and 15.")
        channels.append(channel)
        for key in ("inverted", "direction_confirmed"):
            if type(settings[key]) is not bool:
                raise RuntimeError(f"servos.{axis}.{key} must be a boolean.")
        for key in SPEED_KEYS:
            pulse = settings[key]
            if type(pulse) is not int or not safe_min <= pulse <= safe_max:
                raise RuntimeError(
                    f"servos.{axis}.{key} must be between {safe_min} and {safe_max} us."
                )
        values = [settings[key] for key in SPEED_KEYS]
        if values != sorted(values, reverse=True):
            raise RuntimeError(f"servos.{axis} pulse values must descend from positive to negative.")
    if len(set(channels)) != len(channels):
        raise RuntimeError("Pan and tilt must use different PCA9685 channels.")


def _require_exact_keys(value: Any, template: Any, path: str) -> None:
    if not isinstance(value, dict) or not isinstance(template, dict):
        return
    unknown = set(value) - set(template)
    missing = set(template) - set(value)
    if unknown or missing:
        details = []
        if unknown:
            details.append(f"unknown {sorted(unknown)}")
        if missing:
            details.append(f"missing {sorted(missing)}")
        raise RuntimeError(f"{path} has {', '.join(details)} keys.")
    for key in template:
        _require_exact_keys(value[key], template[key], f"{path}.{key}")


def _validate_center(center: Any, camera: dict[str, Any]) -> None:
    if center is None:
        return
    required = {"position", "size", "format", "hflip", "vflip", "legacy"}
    if not isinstance(center, dict) or set(center) != required:
        raise RuntimeError("camera.true_center has invalid calibration metadata.")
    position = center["position"]
    size = center["size"]
    if (
        not isinstance(position, list)
        or len(position) != 2
        or any(type(value) is not int for value in position)
        or size != camera["size"]
        or center["format"] != camera["format"]
        or center["hflip"] != camera["hflip"]
        or center["vflip"] != camera["vflip"]
        or type(center["legacy"]) is not bool
    ):
        raise RuntimeError("Camera center does not match the configured stream and transform.")
    if not 0 <= position[0] < size[0] or not 0 <= position[1] < size[1]:
        raise RuntimeError("Camera center lies outside the configured frame.")
