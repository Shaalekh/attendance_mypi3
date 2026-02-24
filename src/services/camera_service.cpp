#include "camera_service.hpp"
#include "../config/settings.hpp"
#include <iostream>

namespace services {

CameraService::CameraService() {
    // Open default camera (index 0).
    // On Raspberry Pi with libcamera, use: cap_.open(0, cv::CAP_V4L2);
    cap_.open(0, cv::CAP_V4L2);
    if (!cap_.isOpened()) {
        // Fall back to default backend
        cap_.open(0);
    }
    if (!cap_.isOpened()) {
        std::cerr << "Error: cannot open camera\n";
        return;
    }
    cap_.set(cv::CAP_PROP_FRAME_WIDTH,  config::CAMERA_WIDTH);
    cap_.set(cv::CAP_PROP_FRAME_HEIGHT, config::CAMERA_HEIGHT);
}

CameraService::~CameraService() {
    release();
}

void CameraService::start() {
    if (running_.load()) return;
    running_.store(true);
    captureThread_ = std::thread(&CameraService::captureLoop, this);
}

void CameraService::release() {
    running_.store(false);
    if (captureThread_.joinable()) {
        captureThread_.join();
    }
    if (cap_.isOpened()) {
        cap_.release();
    }
}

bool CameraService::getFrame(cv::Mat& frame) const {
    std::lock_guard<std::mutex> lock(frameMutex_);
    if (latestFrame_.empty()) return false;
    latestFrame_.copyTo(frame);
    return true;
}

void CameraService::captureLoop() {
    cv::Mat tmp;
    while (running_.load()) {
        if (cap_.read(tmp) && !tmp.empty()) {
            std::lock_guard<std::mutex> lock(frameMutex_);
            tmp.copyTo(latestFrame_);
        }
    }
}

} // namespace services
