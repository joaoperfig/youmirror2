"""Grab one camera frame, detect a face, and save an annotated image."""

from pathlib import Path

from camera_control import FaceDetector, MirrorCamera


OUTPUT_PATH = Path("camera_test.jpg")


def main() -> None:
    with MirrorCamera() as camera:
        frame = camera.capture_frame()
    detector = FaceDetector()
    face = detector.detect(frame)

    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("OpenCV is required to save the camera test frame.") from error

    # Frames are RGB; OpenCV's image writer expects BGR.
    image = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    if face is None:
        print("No face detected.")
    else:
        cv2.rectangle(image, (face.x, face.y), (face.x + face.width, face.y + face.height), (0, 255, 0), 2)
        print(f"Face center: {face.center}")
    if not cv2.imwrite(str(OUTPUT_PATH), image):
        raise RuntimeError(f"Could not save {OUTPUT_PATH}")
    print(f"Saved {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
