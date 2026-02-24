#ifndef SERVICES_CAMERA_SERVICE_HPP
#define SERVICES_CAMERA_SERVICE_HPP

#include <atomic>
#include <mutex>
#include <thread>
#include <opencv2/videoio.hpp>
#include <opencv2/core.hpp>

namespace services {

/// Continuously captures frames from the camera in a dedicated thread.
class CameraService {
public:
    CameraService();
    ~CameraService();

    CameraService(const CameraService&) = delete;
    CameraService& operator=(const CameraService&) = delete;

    /// Start the capture thread.
    void start();

    /// Stop the capture thread and release the camera.
    void release();

    /// Get the most recent frame (thread-safe).
    /// Returns true if a valid frame was copied into @p frame.
    bool getFrame(cv::Mat& frame) const;

private:
    void captureLoop();

    cv::VideoCapture cap_;
    mutable std::mutex frameMutex_;
    cv::Mat latestFrame_;
    std::thread captureThread_;
    std::atomic<bool> running_{false};
};

} // namespace services

#endif // SERVICES_CAMERA_SERVICE_HPP
