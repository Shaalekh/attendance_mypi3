cmake_minimum_required(VERSION 3.16)
project(attendance_system VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── ARM Cortex-A53 optimizations (Raspberry Pi 3) ──────────────────────────
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64")
    # 64-bit ARM: NEON is always enabled; just set the CPU target
    add_compile_options(-mcpu=cortex-a53 -O2)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "arm")
    # 32-bit ARM: explicitly enable NEON and hard float
    add_compile_options(
        -mcpu=cortex-a53
        -mfpu=neon-fp-armv8
        -mfloat-abi=hard
        -O2
    )
endif()

# Enable threading support
set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

# ── Dependencies ────────────────────────────────────────────────────────────
find_package(OpenCV REQUIRED COMPONENTS core imgproc objdetect highgui videoio imgcodecs)
find_package(AWSSDK REQUIRED COMPONENTS rekognition)

# ── Sources ─────────────────────────────────────────────────────────────────
set(SOURCES
    src/main.cpp
    src/services/camera_service.cpp
    src/services/face_service.cpp
    src/services/aws_service.cpp
    src/ui/main_window.cpp
)

add_executable(attendance_system ${SOURCES})

target_include_directories(attendance_system PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${OpenCV_INCLUDE_DIRS}
)

target_link_libraries(attendance_system PRIVATE
    ${OpenCV_LIBS}
    ${AWSSDK_LINK_LIBRARIES}
    Threads::Threads
)
