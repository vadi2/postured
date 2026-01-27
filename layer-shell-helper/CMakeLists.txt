cmake_minimum_required(VERSION 3.25.1)
project(postured-layer-shell-helper VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets)
find_package(LayerShellQt REQUIRED)

add_executable(postured-layer-shell-helper
    main.cpp
    overlaywindow.cpp
    overlaywindow.h
)

target_link_libraries(postured-layer-shell-helper PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    LayerShellQt::Interface
)

install(TARGETS postured-layer-shell-helper DESTINATION bin)
