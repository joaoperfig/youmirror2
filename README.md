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

> **Safety:** The servos are mechanically limited at their travel boundaries.
> Calibrate and test movement carefully to avoid driving the assembly into a
> limit.

## How tracking works

The camera is mounted behind and mechanically attached to the mirror, looking
through it. This fixed arrangement lets the software use camera-frame pixels
to control mirror movement directly.

Camera calibration records a **true center** pixel: the face position at which
the person is facing the mirror head-on and sees their reflection centered.
During tracking, each frame is scanned for a face and its offset from this
pixel determines the pan and tilt speed:

- At true center: both servos stop.
- A small offset: the corresponding servos move slowly.
- A large offset: the corresponding servos move quickly.

If calibration has not been run, the geometric center of the camera frame is
used. If no face is detected, both servos stop.

## Setup

Install camera and vision support on Raspberry Pi OS:

```bash
sudo apt install python3-picamera2 python3-opencv
```

Install the Waveshare Servo HAT driver:

```bash
pip install Adafruit-PCA9685
```

## Calibrate and run

```bash
# 1. Record the pan and tilt servo control values.
python servo_callibrate.py

# 2. With the mirror mounted, save the face position that centers reflection.
python camera_callibrate.py

# 3. Start live tracking. Press Ctrl+C to stop.
python main.py
```

Calibration is saved in `mirror_config.json`; retain it with its matching
mirror and servo assembly.

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