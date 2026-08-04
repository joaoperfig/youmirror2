"""Live face tracking: move the mirror until the face reaches true center."""

from __future__ import annotations

import time

from camera_control import FaceDetector, MirrorCamera
from project_config import load_config
from servo_control import ServoController


DEAD_ZONE_PIXELS = 15
FAST_DISTANCE_FRACTION = 0.30


def speed_for_offset(offset: int, frame_extent: int, inverted: bool = False) -> str:
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
    return f"{magnitude}_{'positive' if positive else 'negative'}"


def main() -> None:
    config = load_config()
    saved_center = config["camera"]["true_center"]
    detector = FaceDetector()
    try:
        with MirrorCamera() as camera, ServoController() as servos:
            print("Face tracking started; press Ctrl+C to stop.")
            while True:
                frame = camera.capture_frame()
                height, width = frame.shape[:2]
                # Until camera calibration is performed, use the geometric
                # frame center exactly as specified.
                true_center = tuple(saved_center) if saved_center else (width // 2, height // 2)
                face = detector.detect(frame)
                if face is None:
                    servos.stop_all()
                else:
                    face_x, face_y = face.center
                    servos.set_speed(
                        "pan", speed_for_offset(face_x - true_center[0], width)
                    )
                    servos.set_speed(
                        "tilt", speed_for_offset(face_y - true_center[1], height, inverted=True)
                    )
                time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nFace tracking stopped; servos stopped.")


if __name__ == "__main__":
    main()
