# Attendance System – Raspberry Pi 3

A real-time face-recognition attendance system designed to run on a Raspberry Pi 3. It captures video from the Pi Camera, detects faces with OpenCV, and identifies them using AWS Rekognition. The result is displayed in a fullscreen Tkinter UI.

## Features

- Fullscreen UI built with Tkinter
- Live camera feed via Picamera2
- Face detection using OpenCV Haar cascades
- Face recognition using AWS Rekognition
- Threaded AWS calls to keep the UI responsive
- Recognition triggered only when a face is large enough (nearby), with a 3-second cooldown
- GPIO config switch support with debounced state changes
- Web-server mode screen that shows the device access URL
- Registration page uses the browser device camera (mobile/desktop) with front/rear switch
- Registration stores explicit `face_id`, names, and automatic registration timestamp

## Project Structure

```
attendance_mypi3/
├── main.py                  # Entry point
├── config/
│   └── settings.py          # Configuration settings
├── services/
│   ├── aws_service.py       # AWS Rekognition integration
│   ├── camera_service.py    # Picamera2 camera capture
│   └── face_service.py      # OpenCV face detection
└── ui/
    └── main_window.py       # Tkinter main window
```

## Requirements

### Hardware

- Raspberry Pi 3
- Raspberry Pi Camera Module (v1, v2, or HQ)

### Software

- Python 3.8+
- [Picamera2](https://github.com/raspberrypi/picamera2)
- OpenCV (`opencv-python` or the system `python3-opencv` package)
- Pillow
- Boto3
- Flask
- RPi.GPIO

Install dependencies:

```bash
pip install -r requirements.txt
```

> **Note:** On Raspberry Pi OS, `picamera2` and `opencv4` are best installed via `apt`:
> ```bash
> sudo apt install python3-picamera2 python3-opencv
> ```

Verify dependencies against your current environment:

```bash
python scripts/check_dependencies.py
```

### AWS Setup

1. Create an AWS Rekognition **Face Collection** named `attendance_collection`:
   ```bash
   aws rekognition create-collection --collection-id attendance_collection
   ```

2. Index the faces you want to recognize (one image per person). Use the person's name as `ExternalImageId`:
   ```bash
   aws rekognition index-faces \
     --collection-id attendance_collection \
     --image "S3Object={Bucket=your-bucket,Name=john_doe.jpg}" \
     --external-image-id "John Doe"
   ```

3. Configure AWS credentials on the Raspberry Pi:
   ```bash
   aws configure
   ```
   Provide your `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and preferred region (e.g. `eu-west-1`).

## Usage

```bash
python main.py
```

The application launches in fullscreen mode. To mark attendance, a person simply walks up close to the camera. Once the face is detected at sufficient size, the system automatically queries AWS Rekognition and displays the recognized name (green) or "Unknown" (red) on screen — no touching or interaction required.

When the GPIO config switch is turned on, the app enters **Web Server Mode** and shows the URL (IP + port) to open in a browser. Turning the switch off and keeping it off for 2 seconds triggers reboot.

In Web Server Mode, open the URL from a phone/laptop browser and allow camera access. The registration page uses that device camera (not the Pi camera): live preview uses browser `getUserMedia` and, on some mobile browsers, requires a secure context (`https://`). Camera permission must be granted in the browser. If live camera preview is unavailable, the page provides a fallback to capture/upload a photo from the device camera or gallery. It supports front/rear switching where available, and requires `face_id`, English name, and optional Hindi name. Registration indexes the face into Rekognition and stores profile metadata with automatic registration timestamp.

Press **Esc** to quit (development mode).

## How It Works

1. `CameraService` continuously captures frames from the Pi Camera at 640 × 480.
2. `MainWindow` processes every third frame to reduce CPU load.
3. `FaceService` runs an OpenCV Haar-cascade detector on a downscaled (320 × 240) copy of the frame.
4. If a detected face is wide enough (> 120 px at original resolution) and the 3-second cooldown has elapsed, a background thread is spawned.
5. `AWSService` encodes the cropped face as JPEG and calls `search_faces_by_image` against the Rekognition collection.
6. The status label is updated with the result.

## License

This project is provided as-is without a specific license. Contact the repository owner for usage permissions.
