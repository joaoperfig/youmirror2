"""Run live face detection and print the detected face positions."""

import time

from camera_control import FaceDetector, MirrorCamera


def main() -> None:
    detector = FaceDetector()
    try:
        with MirrorCamera() as camera:
            print("Tracking faces; press Ctrl+C to stop.")
            while True:
                face = detector.detect(camera.capture_frame())
                print("No face detected" if face is None else f"Face center: {face.center}")
                time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
