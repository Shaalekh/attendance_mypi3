#ifndef UI_MAIN_WINDOW_HPP
#define UI_MAIN_WINDOW_HPP

#include <atomic>
#include <mutex>
#include <string>
#include <chrono>

#include "../services/camera_service.hpp"
#include "../services/face_service.hpp"
#include "../services/aws_service.hpp"

namespace ui {

/// Fullscreen window that displays the camera feed, detects faces,
/// and triggers AWS Rekognition in a background thread.
///
/// Threading model (optimized for quad-core ARM Cortex A53):
///   Thread 1 – Camera capture   (CameraService::captureLoop)
///   Thread 2 – Face detection    (detectionLoop)
///   Thread 3 – AWS recognition   (awsThread, spawned on demand)
///   Main     – UI rendering      (run / OpenCV highgui)
class MainWindow {
public:
    MainWindow();
    ~MainWindow();

    MainWindow(const MainWindow&) = delete;
    MainWindow& operator=(const MainWindow&) = delete;

    /// Enter the main UI loop (blocks until user presses ESC).
    void run();

private:
    /// Background loop that pulls frames and runs face detection.
    void detectionLoop();

    /// Spawned per-recognition; calls AWS and stores the result.
    void awsThread(cv::Mat faceCrop);

    // Services
    services::CameraService camera_;
    services::FaceService   faceService_;
    services::AWSService    awsService_;

    // Detection thread
    std::thread detectionThread_;
    std::atomic<bool> running_{false};

    // Shared state between detection thread and main thread
    mutable std::mutex statusMutex_;
    std::string statusText_  = "Ready";
    int         statusColor_ = 0; // 0=white, 1=green, 2=red, 3=orange

    // Recognition gating
    std::atomic<bool> processing_{false};
    std::chrono::steady_clock::time_point lastCheck_;

    // Track the active AWS thread for clean shutdown
    std::mutex awsThreadMutex_;
    std::thread awsThread_active_;
};

} // namespace ui

#endif // UI_MAIN_WINDOW_HPP
