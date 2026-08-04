"""Save the detected face position as the mirror's true camera-frame center."""

import time
from statistics import median

from camera_control import FaceDetector, FaceTracker, MirrorCamera
from project_config import load_config, save_config


def main() -> None:
    config = load_config()
    camera_config = config["camera"]
    detector = FaceDetector()
    tracker = FaceTracker(max_missing_s=0.2, smoothing=0.5)
    print(
        "Position yourself facing the mirror head-on with your reflection centered. "
        "Capturing in 5 seconds..."
    )
    samples: list[tuple[int, int]] = []
    with MirrorCamera(
        size=tuple(camera_config["size"]),
        hflip=camera_config["hflip"],
        vflip=camera_config["vflip"],
    ) as camera:
        # Camera exposure settles while the user gets into position.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            camera.capture_frame()
            time.sleep(0.1)
        for _ in range(25):
            captured = camera.capture_frame()
            height, width = captured.image.shape[:2]
            face = tracker.update(
                detector.detect_all(captured.image),
                (width, height),
                captured.captured_monotonic,
            )
            if face is not None:
                samples.append(face.center)
            time.sleep(0.08)
    if len(samples) < 15:
        raise RuntimeError(
            f"Only {len(samples)} stable face samples were found; calibration was not changed."
        )

    center = (round(median(x for x, _ in samples)), round(median(y for _, y in samples)))
    spread_x = median(abs(x - center[0]) for x, _ in samples)
    spread_y = median(abs(y - center[1]) for _, y in samples)
    if spread_x > width * 0.03 or spread_y > height * 0.03:
        raise RuntimeError("Face position was not stable; calibration was not changed.")
    config["camera"]["true_center"] = {
        "position": list(center),
        "size": [width, height],
        "format": camera_config["format"],
        "hflip": camera_config["hflip"],
        "vflip": camera_config["vflip"],
        "legacy": False,
    }
    save_config(config)
    print(f"Saved true center pixel position: {center} from {len(samples)} samples.")


if __name__ == "__main__":
    main()
