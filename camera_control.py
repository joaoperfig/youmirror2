"""Camera capture and fast face detection for the mirror.

Picamera2 supplies RGB frames from the Raspberry Pi camera.  Detection uses
OpenCV's built-in Haar cascade because it is fast enough for a Pi Zero 2 W
and needs no model download.  The largest detected face is treated as the
person using the mirror.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Face:
    """A detected face rectangle and its center in camera-frame pixels."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


class MirrorCamera:
    """Owns the Pi camera lifecycle and returns RGB camera frames."""

    def __init__(self, size: tuple[int, int] = (640, 480)) -> None:
        self.size = size
        self._camera = None

    def start(self) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as error:
            raise RuntimeError(
                "Picamera2 is required on the Raspberry Pi. Install it with "
                "'sudo apt install python3-picamera2'."
            ) from error
        self._camera = Picamera2()
        configuration = self._camera.create_preview_configuration(
            main={"size": self.size, "format": "RGB888"}
        )
        self._camera.configure(configuration)
        self._camera.start()

    def capture_frame(self):
        if self._camera is None:
            raise RuntimeError("Camera has not been started.")
        return self._camera.capture_array("main")

    def close(self) -> None:
        if self._camera is not None:
            self._camera.stop()
            self._camera.close()
            self._camera = None

    def __enter__(self) -> "MirrorCamera":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class FaceDetector:
    """Detect faces and select the largest result for stable tracking."""

    def __init__(self) -> None:
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError(
                "OpenCV is required. Install it with 'sudo apt install python3-opencv'."
            ) from error
        self.cv2 = cv2
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)
        if self._cascade.empty():
            raise RuntimeError(f"Could not load face detection model: {cascade_path}")

    def detect(self, rgb_frame) -> Optional[Face]:
        gray = self.cv2.cvtColor(rgb_frame, self.cv2.COLOR_RGB2GRAY)
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40)
        )
        if len(faces) == 0:
            return None
        x, y, width, height = max(faces, key=lambda rectangle: rectangle[2] * rectangle[3])
        return Face(int(x), int(y), int(width), int(height))
