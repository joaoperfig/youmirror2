# YouMirror

A Raspberry Pi-powered, face-tracking mirror. It moves continuous-rotation pan
and tilt servos to keep a person's reflection centered.

The original project description and specification are preserved verbatim in
[`ORIGINAL_SPECIFICATION.txt`](ORIGINAL_SPECIFICATION.txt).

## Hardware

- Raspberry Pi Zero 2 W running 64-bit Raspberry Pi OS
- Waveshare Servo HAT for Raspberry Pi
- Two continuous-rotation MG90S micro servos
  - Pan / horizontal control: channel 0
  - Tilt / vertical control: channel 1
- Raspberry Pi Camera rev. 1.3

> **Safety:** A software lease returns both outputs to neutral if tracking stops
> refreshing them, and each axis pauses after two seconds of uninterrupted
> same-direction movement. This reduces risk but cannot protect against
> `SIGKILL`, an operating-system/I²C lockup, loss of Pi power, or a failed PWM
> controller. Do not rely on mechanical hard stops as a long-term travel limit.

Confirm the exact continuous-rotation servo manufacturer/SKU before use:
standard positional MG90S servos do not interpret these pulses as speed.
Approximately 1500 µs must stop the installed model.

The HAT uses 3.3 V I²C logic and 5 V servo power. Confirm the power topology
for the exact Waveshare HAT revision. Use a suitably rated servo supply,
decoupling, and a common ground; two stalled micro servos can exceed 1.5 A and
reset the Pi. If using an independent supply, follow the board documentation
for its 0 Ω power link before connecting VIN. The servo header order is
black/brown (ground), red (power), yellow/orange (signal); reversing a connector
can damage hardware. Keep motor leads away from the camera ribbon and provide
strain relief.

## How tracking works

The camera is mounted behind and mechanically attached to the mirror, looking
through it. This fixed arrangement lets the software use camera-frame pixels
to control mirror movement directly.

Camera calibration records a **true center** pixel: the face position at which
the person is facing the mirror head-on and sees their reflection centered.
It records the resolution and camera transform too, and is rejected if those
settings no longer match. Calibration uses multiple stable detections rather
than one startup frame.
During tracking, each frame is scanned for a face and its offset from this
pixel determines the pan and tilt speed:

- At true center: both servos stop.
- A small offset: the corresponding servos move slowly.
- A large offset: the corresponding servos move quickly.

If calibration has not been run, the geometric center of the camera frame is
used. If no face is detected, a frame is stale, or the tracked face jumps
implausibly, both servos stop. Tracking keeps the nearest prior face and smooths
its position to avoid switching abruptly between people.

## Setup

These instructions target 64-bit Raspberry Pi OS Bookworm and Python 3.11.
Enable I²C and verify the default HAT address:

```bash
sudo raspi-config
sudo apt update
sudo apt install python3-picamera2 python3-opencv python3-venv i2c-tools
i2cdetect -y 1
```

`0x40` should appear in the scan. If the HAT address jumpers were changed,
update `servos.i2c_address` in `mirror_config.json`.

Raspberry Pi OS applies PEP 668 and Picamera2/OpenCV are installed by `apt`.
Create a virtual environment that can see those system packages, then install
the maintained CircuitPython PCA9685 driver and Blinka:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements-pi.txt
```

Do not install the archived `Adafruit-PCA9685` package; this project uses
`adafruit-circuitpython-pca9685`.

## Calibrate and run

```bash
# 1. Record the pan and tilt servo control values.
python3 servo_callibrate.py

# 2. With the mirror mounted, save the face position that centers reflection.
python3 camera_callibrate.py

# 3. Start live tracking. Press Ctrl+C to stop.
python3 main.py
```

Calibration is saved in `mirror_config.json`; retain it with its matching
mirror, camera resolution/transform, servo model, and servo assembly. Existing
tick-based configuration is migrated from 50 Hz to microseconds when loaded.

Direction defaults preserve the original mounting assumption (pan normal,
tilt inverted), but tracking prints a warning until each direction is confirmed
by `servo_callibrate.py`.

## Camera troubleshooting

Run `libcamera-hello` (or `rpicam-hello` on newer images) to verify camera
detection, then run `python3 camera_test.py`. Picamera2's `RGB888` stream is
BGR byte order in memory due to libcamera/DRM naming; the code intentionally
passes it directly to OpenCV. In `camera_test.jpg`, red and blue objects should
have the correct colors. Check camera ribbon orientation, overlays, and
`/boot/firmware/config.txt` only if the camera tools cannot detect the sensor.

Run the hardware-free regression suite with:

```bash
python3 -m unittest test_safety.py
```

## Scripts

- `camera_control.py` — camera capture and face-detection functions.
- `servo_control.py` — Waveshare Servo HAT control functions.
- `camera_test.py` — captures a frame, detects a face, and saves the result.
- `camera_track.py` — runs live face detection and prints face positions.
- `camera_callibrate.py` — saves a detected face position as true center.
- `servo_test.py` — interactive servo test: `w`, `a`, `s`, `d` move slowly;
  uppercase `W`, `A`, `S`, `D` move quickly. Works through SSH.
- `servo_callibrate.py` — records the five control values for each servo:
  `fast_positive_speed`, `slow_positive_speed`, `stopped_speed`,
  `slow_negative_speed`, and `fast_negative_speed`.
- `main.py` — runs the face-tracking loop and controls both servos.