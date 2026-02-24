#ifndef CONFIG_SETTINGS_HPP
#define CONFIG_SETTINGS_HPP

#include <string>

namespace config {

// Camera settings
constexpr int CAMERA_WIDTH  = 640;
constexpr int CAMERA_HEIGHT = 480;

// Face detection settings (applied on downscaled frame)
constexpr int DETECT_WIDTH  = 320;
constexpr int DETECT_HEIGHT = 240;
constexpr double SCALE_FACTOR   = 1.2;
constexpr int    MIN_NEIGHBORS  = 5;
constexpr int    MIN_FACE_SIZE  = 80;

// Recognition trigger: minimum face width at original resolution
constexpr int MIN_FACE_WIDTH_TRIGGER = 120;

// Cooldown between AWS recognition calls (seconds)
constexpr double RECOGNITION_COOLDOWN_SEC = 3.0;

// Process every Nth frame for detection
constexpr int DETECT_FRAME_INTERVAL = 3;

// UI refresh interval (milliseconds)
constexpr int UI_REFRESH_MS = 30;

// UI text overlay settings
constexpr double FONT_SCALE     = 1.0;
constexpr int    FONT_THICKNESS = 2;

// AWS Rekognition settings
const std::string COLLECTION_ID = "attendance_collection";
constexpr int     MAX_FACES     = 1;
constexpr float   FACE_MATCH_THRESHOLD = 80.0f;

// Haar cascade path (default for Raspberry Pi OS with OpenCV 4)
const std::string HAAR_CASCADE_PATH =
    "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml";

} // namespace config

#endif // CONFIG_SETTINGS_HPP
