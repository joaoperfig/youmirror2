"""Grab one camera frame, detect a face, and save an annotated image."""

from pathlib import Path

from camera_control import FaceDetector, MirrorCamera
from project_config import load_config


OUTPUT_PATH = Path("camera_test.jpg")


def main() -> None:
    config = load_config()["camera"]
    with MirrorCamera(
        size=tuple(config["size"]),
        hflip=config["hflip"],
        vflip=config["vflip"],
    ) as camera:
        captured = camera.capture_frame()
    frame = captured.image
    detector = FaceDetector()
    face = detector.detect(frame)

    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCV is required to save the camera test frame.") from error

    # Picamera2 RGB888 arrays are already in OpenCV's BGR byte order.
    image = frame.copy()
    if face is None:
        print("No face detected.")
    else:
        cv2.rectangle(image, (face.x, face.y), (face.x + face.width, face.y + face.height), (0, 255, 0), 2)
        print(f"Face center: {face.center}")
    if not cv2.imwrite(str(OUTPUT_PATH), image):
        raise RuntimeError(f"Could not save {OUTPUT_PATH}")
    print(
        f"Frame age: {captured.age * 1000:.1f} ms; "
        f"sensor timestamp: {captured.sensor_timestamp_ns}"
    )
    print(f"Saved {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
