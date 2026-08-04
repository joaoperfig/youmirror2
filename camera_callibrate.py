"""Save the detected face position as the mirror's true camera-frame center."""

import time

from camera_control import FaceDetector, MirrorCamera
from project_config import load_config, save_config


def main() -> None:
    print(
        "Position yourself facing the mirror head-on with your reflection centered. "
        "Capturing in 5 seconds..."
    )
    time.sleep(5)
    detector = FaceDetector()
    with MirrorCamera() as camera:
        frame = camera.capture_frame()
    face = detector.detect(frame)
    if face is None:
        raise RuntimeError("No face detected; calibration was not changed.")

    config = load_config()
    config["camera"]["true_center"] = list(face.center)
    save_config(config)
    print(f"Saved true center pixel position: {face.center}")


if __name__ == "__main__":
    main()
