"""Live face tracking: move the mirror until the face reaches true center."""

from __future__ import annotations

import time
import signal
from typing import cast

from camera_control import FaceDetector, FaceTracker, MirrorCamera
from project_config import load_config
from servo_control import ServoController, Speed


DEAD_ZONE_PIXELS = 15
FAST_DISTANCE_FRACTION = 0.30
MAX_FRAME_AGE_S = 0.35


def speed_for_offset(offset: int, frame_extent: int, inverted: bool = False) -> Speed:
    """Convert a face-to-center vector component into a calibrated speed.

    Pan follows horizontal pixel direction.  The camera/mirror layout makes
    tilt opposite vertical pixel direction: a face below center needs negative
    tilt, while a face above center needs positive tilt.
    """
    if abs(offset) <= DEAD_ZONE_PIXELS:
        return "stopped"
    magnitude = "fast" if abs(offset) >= frame_extent * FAST_DISTANCE_FRACTION else "slow"
    positive = offset > 0
    if inverted:
        positive = not positive
    return cast(Speed, f"{magnitude}_{'positive' if positive else 'negative'}")


def _request_stop(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main() -> None:
    config = load_config()
    saved_center = config["camera"]["true_center"]
    camera_config = config["camera"]
    servo_config = config["servos"]
    for signal_name in ("SIGTERM", "SIGHUP"):
        shutdown_signal = getattr(signal, signal_name, None)
        if shutdown_signal is not None:
            signal.signal(shutdown_signal, _request_stop)
    unconfirmed = [
        axis for axis in ("pan", "tilt") if not servo_config[axis]["direction_confirmed"]
    ]
    if unconfirmed:
        print(
            "WARNING: using unconfirmed default direction for "
            f"{', '.join(unconfirmed)}; run servo_callibrate.py."
        )
    if saved_center and saved_center["legacy"]:
        print("WARNING: camera center was migrated without measured metadata; recalibrate it.")
    detector = FaceDetector()
    tracker = FaceTracker()
    try:
        with MirrorCamera(
            size=tuple(camera_config["size"]),
            hflip=camera_config["hflip"],
            vflip=camera_config["vflip"],
        ) as camera, ServoController(config) as servos:
            print("Face tracking started; press Ctrl+C to stop.")
            while True:
                captured = camera.capture_frame()
                frame = captured.image
                height, width = frame.shape[:2]
                # Until camera calibration is performed, use the geometric
                # frame center exactly as specified.
                true_center = (
                    tuple(saved_center["position"])
                    if saved_center
                    else (width // 2, height // 2)
                )
                faces = detector.detect_all(frame)
                face = tracker.update(faces, (width, height), captured.captured_monotonic)
                if face is None or captured.age > MAX_FRAME_AGE_S:
                    servos.stop_all()
                else:
                    face_x, face_y = face.center
                    servos.set_speeds(
                        speed_for_offset(
                            face_x - true_center[0],
                            width,
                            inverted=servo_config["pan"]["inverted"],
                        ),
                        speed_for_offset(
                            face_y - true_center[1],
                            height,
                            inverted=servo_config["tilt"]["inverted"],
                        ),
                    )
                time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nFace tracking stopped; servos stopped.")


if __name__ == "__main__":
    main()
