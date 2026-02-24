#include <aws/core/Aws.h>
#include <iostream>
#include "ui/main_window.hpp"

int main() {
    // Initialize the AWS SDK (must outlive all AWS client usage)
    Aws::SDKOptions options;
    Aws::InitAPI(options);

    try {
        ui::MainWindow app;
        app.run();
    } catch (const std::exception& e) {
        std::cerr << "Fatal: " << e.what() << "\n";
    }

    Aws::ShutdownAPI(options);
    return 0;
}
