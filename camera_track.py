"""Run live face detection and print the detected face positions."""

import time

from camera_control import FaceDetector, FaceTracker, MirrorCamera
from project_config import load_config


def main() -> None:
    config = load_config()["camera"]
    detector = FaceDetector()
    tracker = FaceTracker()
    try:
        with MirrorCamera(
            size=tuple(config["size"]),
            hflip=config["hflip"],
            vflip=config["vflip"],
        ) as camera:
            print("Tracking faces; press Ctrl+C to stop.")
            while True:
                captured = camera.capture_frame()
                height, width = captured.image.shape[:2]
                face = tracker.update(
                    detector.detect_all(captured.image),
                    (width, height),
                    captured.captured_monotonic,
                )
                print("No face detected" if face is None else f"Face center: {face.center}")
                time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
