#ifndef SERVICES_FACE_SERVICE_HPP
#define SERVICES_FACE_SERVICE_HPP

#include <vector>
#include <opencv2/objdetect.hpp>
#include <opencv2/core.hpp>

namespace services {

/// Detects faces using an OpenCV Haar cascade classifier.
class FaceService {
public:
    FaceService();

    /// Detect faces in the given frame.
    /// Returns a vector of bounding rectangles.
    std::vector<cv::Rect> detectFaces(const cv::Mat& frame);

private:
    cv::CascadeClassifier cascade_;
};

} // namespace services

#endif // SERVICES_FACE_SERVICE_HPP
