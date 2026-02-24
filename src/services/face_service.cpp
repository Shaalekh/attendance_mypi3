#include "face_service.hpp"
#include "../config/settings.hpp"
#include <opencv2/imgproc.hpp>
#include <iostream>

namespace services {

FaceService::FaceService() {
    if (!cascade_.load(config::HAAR_CASCADE_PATH)) {
        std::cerr << "Error: cannot load Haar cascade from "
                  << config::HAAR_CASCADE_PATH << "\n";
    }
}

std::vector<cv::Rect> FaceService::detectFaces(const cv::Mat& frame) {
    std::vector<cv::Rect> faces;
    cv::Mat gray;
    cv::cvtColor(frame, gray, cv::COLOR_BGR2GRAY);
    cascade_.detectMultiScale(
        gray,
        faces,
        config::SCALE_FACTOR,
        config::MIN_NEIGHBORS,
        0,
        cv::Size(config::MIN_FACE_SIZE, config::MIN_FACE_SIZE)
    );
    return faces;
}

} // namespace services
