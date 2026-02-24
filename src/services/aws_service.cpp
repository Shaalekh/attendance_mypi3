#include "aws_service.hpp"
#include "../config/settings.hpp"

#include <opencv2/imgcodecs.hpp>
#include <iostream>
#include <vector>

#include <aws/core/Aws.h>
#include <aws/rekognition/RekognitionClient.h>
#include <aws/rekognition/model/SearchFacesByImageRequest.h>
#include <aws/core/utils/Array.h>

namespace services {

AWSService::AWSService() {
    Aws::Client::ClientConfiguration clientCfg;
    // Region is picked up from ~/.aws/config or AWS_DEFAULT_REGION
    client_ = std::make_unique<Aws::Rekognition::RekognitionClient>(clientCfg);
}

AWSService::~AWSService() = default;

std::optional<std::string> AWSService::recognizeFace(const cv::Mat& faceCrop) {
    // Encode face crop to JPEG
    std::vector<unsigned char> buf;
    if (!cv::imencode(".jpg", faceCrop, buf)) {
        std::cerr << "Error: failed to encode face crop to JPEG\n";
        return std::nullopt;
    }

    // Build the Rekognition request
    Aws::Rekognition::Model::Image image;
    Aws::Utils::ByteBuffer byteBuffer(buf.data(), buf.size());
    image.SetBytes(std::move(byteBuffer));

    Aws::Rekognition::Model::SearchFacesByImageRequest request;
    request.SetCollectionId(config::COLLECTION_ID.c_str());
    request.SetImage(std::move(image));
    request.SetMaxFaces(config::MAX_FACES);
    request.SetFaceMatchThreshold(config::FACE_MATCH_THRESHOLD);

    auto outcome = client_->SearchFacesByImage(request);
    if (!outcome.IsSuccess()) {
        std::cerr << "AWS Rekognition error: "
                  << outcome.GetError().GetMessage() << "\n";
        return std::nullopt;
    }

    const auto& matches = outcome.GetResult().GetFaceMatches();
    if (!matches.empty()) {
        return std::string(matches[0].GetFace().GetExternalImageId().c_str());
    }
    return std::nullopt;
}

} // namespace services
