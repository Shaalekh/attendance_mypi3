#include "main_window.hpp"
#include "../config/settings.hpp"

#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>
#include <iostream>
#include <thread>

namespace ui {

static const char* WINDOW_NAME = "Attendance System";

MainWindow::MainWindow()
    : lastCheck_(std::chrono::steady_clock::now() -
                 std::chrono::seconds(10)) // allow immediate first check
{
}

MainWindow::~MainWindow() {
    running_.store(false);
    if (detectionThread_.joinable()) {
        detectionThread_.join();
    }
    // Join the outstanding AWS thread if any
    {
        std::lock_guard<std::mutex> lock(awsThreadMutex_);
        if (awsThread_active_.joinable()) {
            awsThread_active_.join();
        }
    }
    camera_.release();
    cv::destroyAllWindows();
}

// ---------------------------------------------------------------------------
// Main UI loop – runs on the main thread
// ---------------------------------------------------------------------------
void MainWindow::run() {
    // Create a fullscreen window
    cv::namedWindow(WINDOW_NAME, cv::WINDOW_NORMAL);
    cv::setWindowProperty(WINDOW_NAME, cv::WND_PROP_FULLSCREEN,
                          cv::WINDOW_FULLSCREEN);

    // Start background threads
    camera_.start();
    running_.store(true);
    detectionThread_ = std::thread(&MainWindow::detectionLoop, this);

    cv::Mat frame;
    while (running_.load()) {
        if (camera_.getFrame(frame)) {
            // Overlay status text
            {
                std::lock_guard<std::mutex> lock(statusMutex_);
                cv::Scalar color;
                switch (statusColor_) {
                    case 1:  color = cv::Scalar(0, 255, 0);   break; // green
                    case 2:  color = cv::Scalar(0, 0, 255);   break; // red
                    case 3:  color = cv::Scalar(0, 165, 255); break; // orange
                    default: color = cv::Scalar(255, 255, 255);      // white
                }
                cv::putText(frame, statusText_, cv::Point(20, 40),
                            cv::FONT_HERSHEY_SIMPLEX, config::FONT_SCALE,
                            color, config::FONT_THICKNESS);
            }

            cv::imshow(WINDOW_NAME, frame);
        }

        // ESC (27) to quit
        int key = cv::waitKey(config::UI_REFRESH_MS);
        if (key == 27) {
            running_.store(false);
        }
    }
}

// ---------------------------------------------------------------------------
// Detection loop – runs on a dedicated thread
// ---------------------------------------------------------------------------
void MainWindow::detectionLoop() {
    cv::Mat frame, small;
    int frameCount = 0;

    while (running_.load()) {
        if (!camera_.getFrame(frame)) {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        ++frameCount;
        if (frameCount % config::DETECT_FRAME_INTERVAL != 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        // Downscale for faster detection
        cv::resize(frame, small,
                   cv::Size(config::DETECT_WIDTH, config::DETECT_HEIGHT));

        auto faces = faceService_.detectFaces(small);

        double scaleX = static_cast<double>(frame.cols) / config::DETECT_WIDTH;
        double scaleY = static_cast<double>(frame.rows) / config::DETECT_HEIGHT;

        for (const auto& f : faces) {
            int x = static_cast<int>(f.x * scaleX);
            int y = static_cast<int>(f.y * scaleY);
            int w = static_cast<int>(f.width  * scaleX);
            int h = static_cast<int>(f.height * scaleY);

            if (w > config::MIN_FACE_WIDTH_TRIGGER) {
                // Atomically claim the processing slot; if another
                // iteration already set it we skip immediately.
                bool expected = false;
                if (!processing_.compare_exchange_strong(expected, true)) {
                    continue;
                }

                auto now = std::chrono::steady_clock::now();
                double elapsed =
                    std::chrono::duration<double>(now - lastCheck_).count();

                if (elapsed <= config::RECOGNITION_COOLDOWN_SEC) {
                    // Still in cooldown – release the flag and skip
                    processing_.store(false);
                    continue;
                }

                lastCheck_ = now;

                // Clamp ROI to frame boundaries
                int x2 = std::min(x + w, frame.cols);
                int y2 = std::min(y + h, frame.rows);
                x = std::max(x, 0);
                y = std::max(y, 0);

                cv::Mat crop = frame(cv::Rect(x, y, x2 - x, y2 - y)).clone();

                // Spawn AWS call on a tracked thread
                {
                    std::lock_guard<std::mutex> lock(awsThreadMutex_);
                    if (awsThread_active_.joinable()) {
                        awsThread_active_.join();
                    }
                    awsThread_active_ = std::thread(
                        &MainWindow::awsThread, this, std::move(crop));
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// AWS recognition – runs on a tracked background thread
// ---------------------------------------------------------------------------
void MainWindow::awsThread(cv::Mat faceCrop) {
    try {
        auto name = awsService_.recognizeFace(faceCrop);
        std::lock_guard<std::mutex> lock(statusMutex_);
        if (name.has_value()) {
            statusText_  = "Recognized: " + name.value();
            statusColor_ = 1; // green
        } else {
            statusText_  = "Unknown";
            statusColor_ = 2; // red
        }
    } catch (const std::exception& e) {
        std::lock_guard<std::mutex> lock(statusMutex_);
        statusText_  = "AWS Error";
        statusColor_ = 3; // orange
        std::cerr << "AWS error: " << e.what() << "\n";
    }
    processing_.store(false);
}

} // namespace ui
