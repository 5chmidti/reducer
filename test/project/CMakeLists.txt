cmake_minimum_required(VERSION 3.10)
project(test_project)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(main)
target_sources(main PRIVATE src/main.cpp)

add_library(ice64454)
target_sources(ice64454 PRIVATE src/ice64454.cpp)
