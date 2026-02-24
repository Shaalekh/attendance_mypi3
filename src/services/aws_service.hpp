#ifndef SERVICES_AWS_SERVICE_HPP
#define SERVICES_AWS_SERVICE_HPP

#include <string>
#include <optional>
#include <opencv2/core.hpp>

namespace Aws { namespace Rekognition { class RekognitionClient; } }

namespace services {

/// Wraps AWS Rekognition face search.
class AWSService {
public:
    AWSService();
    ~AWSService();

    AWSService(const AWSService&) = delete;
    AWSService& operator=(const AWSService&) = delete;

    /// Search for a matching face in the collection.
    /// Returns the ExternalImageId if a match is found, or std::nullopt.
    std::optional<std::string> recognizeFace(const cv::Mat& faceCrop);

private:
    std::unique_ptr<Aws::Rekognition::RekognitionClient> client_;
};

} // namespace services

#endif // SERVICES_AWS_SERVICE_HPP
