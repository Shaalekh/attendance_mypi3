# Attendance System – Raspberry Pi 3

A real-time face-recognition attendance system designed to run on a Raspberry Pi 3. It captures video from the Pi Camera, detects faces with OpenCV, and identifies them using AWS Rekognition. The result is displayed in a fullscreen Tkinter UI.

## Features

- Fullscreen UI built with Tkinter
- Live camera feed via Picamera2
- Face detection using OpenCV Haar cascades
- Face recognition using AWS Rekognition
- Threaded AWS calls to keep the UI responsive
- Recognition triggered only when a face is large enough (nearby), with a 3-second cooldown

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

Install dependencies:

```bash
pip install boto3 opencv-python pillow picamera2
```

> **Note:** On Raspberry Pi OS, `picamera2` and `opencv4` are best installed via `apt`:
> ```bash
> sudo apt install python3-picamera2 python3-opencv
> ```

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
