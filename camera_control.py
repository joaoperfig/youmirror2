"""Picamera2 capture, OpenCV face detection, and continuity-aware tracking."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


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


@dataclass(frozen=True)
class CapturedFrame:
    """A BGR frame and the timing/stream metadata needed to validate it."""

    image: Any
    captured_monotonic: float
    sensor_timestamp_ns: int | None
    metadata: dict[str, Any]

    @property
    def age(self) -> float:
        return max(0.0, time.monotonic() - self.captured_monotonic)


class MirrorCamera:
    """Own the Pi camera lifecycle and return BGR arrays via RGB888."""

    def __init__(
        self,
        size: tuple[int, int] = (640, 480),
        hflip: bool = False,
        vflip: bool = False,
    ) -> None:
        self.size = size
        self.hflip = hflip
        self.vflip = vflip
        self._camera = None

    def start(self) -> None:
        if self._camera is not None:
            raise RuntimeError("Camera is already started.")
        try:
            from picamera2 import Picamera2
            from libcamera import Transform
        except ImportError as error:
            raise RuntimeError(
                "Picamera2 is required on the Raspberry Pi. Install it with "
                "'sudo apt install python3-picamera2'."
            ) from error
        camera = Picamera2()
        try:
            configuration = camera.create_preview_configuration(
                main={"size": self.size, "format": "RGB888"},
                transform=Transform(hflip=self.hflip, vflip=self.vflip),
                queue=False,
                buffer_count=2,
            )
            camera.configure(configuration)
            camera.start()
        except Exception:
            try:
                self._close_camera(camera)
            except Exception:
                pass
            raise
        self._camera = camera

    def capture_frame(self) -> CapturedFrame:
        camera = self._camera
        if camera is None:
            raise RuntimeError("Camera has not been started.")
        request = camera.capture_request()
        try:
            image = request.make_array("main")
            metadata = dict(request.get_metadata())
            received = time.monotonic()
        finally:
            request.release()
        sensor_timestamp = metadata.get("SensorTimestamp")
        return CapturedFrame(
            image=image,
            captured_monotonic=received,
            sensor_timestamp_ns=(
                int(sensor_timestamp) if sensor_timestamp is not None else None
            ),
            metadata=metadata,
        )

    def close(self) -> None:
        camera, self._camera = self._camera, None
        if camera is not None:
            self._close_camera(camera)

    @staticmethod
    def _close_camera(camera: Any) -> None:
        first_error: Exception | None = None
        try:
            camera.stop()
        except Exception as error:
            first_error = error
        try:
            camera.close()
        except Exception as error:
            first_error = first_error or error
        if first_error is not None:
            raise first_error

    def __enter__(self) -> "MirrorCamera":
        self.start()
        return self

    def __exit__(self, exception_type: object, *_: object) -> None:
        if exception_type is None:
            self.close()
            return
        try:
            self.close()
        except Exception:
            pass


class FaceDetector:
    """Detect frontal faces in Picamera2 RGB888 (BGR byte-order) arrays."""

    def __init__(self) -> None:
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError(
                "OpenCV is required. Install it with 'sudo apt install python3-opencv'."
            ) from error
        self.cv2 = cv2
        filename = "haarcascade_frontalface_default.xml"
        cv2_data = getattr(cv2, "data", None)
        candidates: list[Path] = []
        if cv2_data is not None and hasattr(cv2_data, "haarcascades"):
            candidates.append(Path(cv2_data.haarcascades) / filename)
        candidates.extend(
            [
                Path("/usr/share/opencv4/haarcascades") / filename,
                Path("/usr/share/opencv/haarcascades") / filename,
            ]
        )
        cascade_path = next((path for path in candidates if path.is_file()), None)
        if cascade_path is None:
            raise RuntimeError(
                "Could not find the OpenCV face detection model. Install it with "
                "'sudo apt install opencv-data'."
            )
        self._cascade = cv2.CascadeClassifier(str(cascade_path))
        if self._cascade.empty():
            raise RuntimeError(f"Could not load face detection model: {cascade_path}")

    def detect_all(self, bgr_frame: Any) -> list[Face]:
        gray = self.cv2.cvtColor(bgr_frame, self.cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40)
        )
        return [
            Face(int(x), int(y), int(width), int(height))
            for x, y, width, height in faces
        ]

    def detect(self, bgr_frame: Any) -> Optional[Face]:
        faces = self.detect_all(bgr_frame)
        return max(faces, key=lambda face: face.width * face.height, default=None)


class FaceTracker:
    """Keep one target across frames and smooth its rectangle."""

    def __init__(
        self,
        max_missing_s: float = 0.30,
        max_jump_fraction: float = 0.25,
        smoothing: float = 0.35,
    ) -> None:
        self.max_missing_s = max_missing_s
        self.max_jump_fraction = max_jump_fraction
        self.smoothing = smoothing
        self._face: Face | None = None
        self._last_seen = 0.0

    def update(
        self, faces: list[Face], frame_size: tuple[int, int], timestamp: float
    ) -> Face | None:
        if not faces:
            if timestamp - self._last_seen > self.max_missing_s:
                self._face = None
            return None
        if self._face is None:
            selected = max(faces, key=lambda face: face.width * face.height)
            self._face = selected
            self._last_seen = timestamp
            return selected
        old_x, old_y = self._face.center
        selected = min(
            faces,
            key=lambda face: (face.center[0] - old_x) ** 2 + (face.center[1] - old_y) ** 2,
        )
        new_x, new_y = selected.center
        maximum_jump = max(frame_size) * self.max_jump_fraction
        if (new_x - old_x) ** 2 + (new_y - old_y) ** 2 > maximum_jump**2:
            return None
        old_area = self._face.width * self._face.height
        new_area = selected.width * selected.height
        if new_area > old_area * 3 or old_area > new_area * 3:
            return None
        alpha = self.smoothing
        self._face = Face(
            x=round(self._face.x * (1 - alpha) + selected.x * alpha),
            y=round(self._face.y * (1 - alpha) + selected.y * alpha),
            width=round(self._face.width * (1 - alpha) + selected.width * alpha),
            height=round(self._face.height * (1 - alpha) + selected.height * alpha),
        )
        self._last_seen = timestamp
        return self._face
