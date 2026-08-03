Raspberry-powered face tracking mirror project.

Hardware info:
Raspberry pi Zero 2W
-Raspberry OS (64 bit)
Waveshare Servo HAT for raspberry pi
2x CONTIUNOUS MG90S micro servo 360º
-horizontal pan control servo on channel 0
-vertical tilt control servo on channel 1
-servos are mounted so that movement is mechanically blocked if they reach a limit
Raspberry pi camera rev 1.3

Implementation info:
To simplify math required for mirror face tracking, camera is mounted behind mirror and sees through it, mechanically attached to the mirror

There is a pre-callibrated "true center" pixel position in the camera frame, where if the detected face is centered on this pixel, then the person will be centered and see themselves on the mirror.

During the update loop, a frame is taken, a fast but sensitive face detection model or algorithm is run, and a face is detected within the frame. the script will calculate the vector that brings the face to the callibrated center. this vector is used to set the servo speeds for this loop iteration. if the face is in position, it is "stopped,stopped" if slightly down and slightly left it is "slow negative, slow negative" if all the way in the top right corner its "fast positive, fast positive", etc.

scripts:
camera_control.py - camera related control functions
servo_control.py - servo control related functions
camera_test.py - grabs frame, detects face, saves frame
camera_track.py - live face detection loop, printing face positions
servo_test.py - live videogame-like control of servos. w-a-s-d control movement at minimum speed, W-A-S-D control movement at max speed. key presses are live captured from terminal and should work via ssh
servo_callibrate.py - script to find ideal frequencies for fast_positive_speed, slow_positive_speed, stopped_speed, fast_negative_speed, slow_negative_speed; for both servos. Assume reasonable values if callibration has not ben done
main.py - main face tracking script with loop that grabs frames, detects faces, and sets servo speeds.