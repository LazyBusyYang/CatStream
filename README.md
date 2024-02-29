# Cat Stream

## Introduction

This project is a multi-perspective cat live streaming program implemented based on Python and OBS Studio. It can select the camera view according to the detection results of cats from multiple RTSP network cameras in the home, control OBS to activate scenes with cats, and complete unattended cat live streaming on the network.

![Rooms, cameras and cat](./resources/room_illustration.jpg)

The main program initializes upon startup according to the configuration file, connects to the OBS websocket server, and enters a while loop. Within each iteration of the loop, it requests the latest RTSP URLs for each perspective from OBS. It then uses ffmpeg or cv2 to read the latest video frames from RTSP. Utilizing YOLOv5 or cv2, it detects whether a cat is present in the video frames. Based on the detection results, it sends scene-switching signals to OBS. The flowchart is shown in the figure below.

![Mainloop flow chart](./resources/mainloop_flow.png)

## Prerequisites

Before you begin, ensure you have met the following requirements:

- **OBS studio**: Please configure the various scenes and RTSP media sources in OBS, and enable OBS websocket. This project merely automates the process of scene switching, not creating.
- **Pytorch**: Pytorch-CPU is required for YOLOv5 cat body detection. Without pytorch, the performance of cv2 cat face detection is relatively poor.
- **FFmpeg command tool**: To read RTSP stream, ffmpeg works perfectly, while cv2 usually reports decoding errors(the program won't crash).

## Installing

Navigate to the root directory of the project, and then directly use pip to install this project. Third-party dependencies will be automatically completed.
```bash
pip install .
```
To run the YOLO object detection with GPU, please refer to the official PyTorch tutorial and modify the device-related section in the configuration file of this project.

## Running

Please write the configuration file needed for live streaming control based on the existing configuration files and runtime environment in the `configs/` directory. For the specific meaning of each value in the configuration file, you can refer to the docstring of the `__init__` function in the code.

When the configuration file is ready, start program with a command like below:
```bash
python tools/main.py --config_path configs/yolov5_ffmpeg_3scenes.py
```


## Authors

* **LazyBusyYang** - [Github Page](https://github.com/LazyBusyYang)

## License

This project is licensed under the Apache 2.0 License
