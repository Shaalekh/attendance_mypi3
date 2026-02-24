# Attendance System – Raspberry Pi 3 (C++)

A real-time face-recognition attendance system designed to run on a **Raspberry Pi 3** (ARM Cortex-A53 quad-core). It captures video from the Pi Camera, detects faces with OpenCV, and identifies them using AWS Rekognition — all written in **C++17** for maximum performance.

## Features

- **Multi-threaded pipeline** optimized for the quad-core ARM Cortex-A53:
  - Thread 1 — Camera capture (continuous, lock-free latest-frame)
  - Thread 2 — Face detection (runs on every 3rd frame, downscaled)
  - Thread 3 — AWS Rekognition (spawned on demand per face)
  - Main thread — UI rendering (OpenCV highgui fullscreen window)
- Fullscreen display with status overlay
- Face detection using OpenCV Haar cascades (C++ API)
- Face recognition using AWS Rekognition (AWS SDK for C++)
- NEON SIMD compiler hints for ARM Cortex-A53
- 3-second cooldown between recognition calls

## Project Structure

```
attendance_mypi3/
├── CMakeLists.txt                # Build system
├── src/
│   ├── main.cpp                  # Entry point (AWS SDK init)
│   ├── config/
│   │   └── settings.hpp          # Compile-time configuration
│   ├── services/
│   │   ├── aws_service.hpp/.cpp  # AWS Rekognition integration
│   │   ├── camera_service.hpp/.cpp # Threaded V4L2 camera capture
│   │   └── face_service.hpp/.cpp # OpenCV face detection
│   └── ui/
│       └── main_window.hpp/.cpp  # Fullscreen UI + detection loop
├── main.py                       # Legacy Python entry point
├── config/                       # Legacy Python config
├── services/                     # Legacy Python services
└── ui/                           # Legacy Python UI
```

## Requirements

### Hardware

- Raspberry Pi 3 (ARM Cortex-A53)
- Raspberry Pi Camera Module (v1, v2, or HQ)

### Software

Install build dependencies on Raspberry Pi OS:

```bash
sudo apt update
sudo apt install -y \
    build-essential cmake \
    libopencv-dev \
    libcurl4-openssl-dev libssl-dev zlib1g-dev
```

Install the AWS SDK for C++ (Rekognition):

```bash
git clone --recurse-submodules https://github.com/aws/aws-sdk-cpp.git
cd aws-sdk-cpp
mkdir build && cd build
cmake .. -DBUILD_ONLY="rekognition" \
         -DCMAKE_BUILD_TYPE=Release \
         -DBUILD_SHARED_LIBS=ON
make -j4
sudo make install
sudo ldconfig
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

## Building

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j4
```

## Usage

```bash
./build/attendance_system
```

The application launches in fullscreen mode. To mark attendance, a person simply walks up close to the camera. Once the face is detected at sufficient size, the system automatically queries AWS Rekognition and displays the recognized name (green) or "Unknown" (red) on screen — no touching or interaction required.

Press **Esc** to quit.

## How It Works

1. `CameraService` runs a dedicated capture thread that continuously grabs frames from the Pi Camera at 640 × 480 via V4L2.
2. `MainWindow::detectionLoop` runs on its own thread, pulling the latest frame and running detection every 3rd iteration.
3. `FaceService::detectFaces` applies the OpenCV Haar-cascade detector on a downscaled (320 × 240) copy of the frame.
4. If a detected face is wide enough (> 120 px at original resolution) and the 3-second cooldown has elapsed, a detached thread is spawned for AWS recognition.
5. `AWSService::recognizeFace` encodes the cropped face as JPEG and calls `SearchFacesByImage` against the Rekognition collection via the AWS SDK for C++.
6. The status text is updated thread-safely and rendered on the next UI frame.

## Performance Notes

- Compiled with `-mcpu=cortex-a53` on ARM targets. On 32-bit ARM OS the build also enables `-mfpu=neon-fp-armv8 -mfloat-abi=hard`; on 64-bit ARM (AArch64) NEON is enabled by default.
- The pipelined multi-threaded design ensures camera capture, face detection, AWS calls, and UI rendering all run concurrently across the four CPU cores.
- Frame processing is lock-minimized: only the latest frame and status text use mutexes, and frame copies use `cv::Mat::copyTo` for efficient deep copies.

## License

This project is provided as-is without a specific license. Contact the repository owner for usage permissions.
