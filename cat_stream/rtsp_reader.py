import cv2
import logging
import numpy as np
import re
import subprocess
from typing import Union


def read_img_from_rtsp_cv2(
    rtsp_url: str,
    logger: Union[None, str,
                  logging.Logger] = None) -> Union[np.ndarray, None]:
    """Read the latest frame from the RTSP stream using OpenCV. Note that
    OpenCV cannot decode HEVC, and it may not always decode H.264 correctly.

    Args:
        rtsp_url (str):
            The url of the RTSP stream.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.

    Returns:
        Union[np.ndarray, None]:
            The latest frame from the RTSP stream,
            whose shape is (height, width, 3).
            If the frame cannot be
            read, None will be returned.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    elif isinstance(logger, str):
        logger = logging.getLogger(logger)
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        logger.error('Failed to open the RTSP stream.')
        return None
    ret, frame = cap.read()
    if ret:
        return frame
    else:
        return None


def read_img_from_rtsp_ffmpeg(
    rtsp_url: str,
    logger: Union[None, str,
                  logging.Logger] = None) -> Union[np.ndarray, None]:
    """Read the latest frame from the RTSP stream using FFmpeg.

    Args:
        rtsp_url (str):
            The url of the RTSP stream.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.

    Returns:
        Union[np.ndarray, None]:
            The latest frame from the RTSP stream,
            whose shape is (height, width, 3).
            If the frame cannot be
            read, None will be returned.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    elif isinstance(logger, str):
        logger = logging.getLogger(logger)
    # FFmpeg command to capture the latest frame from RTSP stream
    ffmpeg_cmd = [
        'ffmpeg',
        '-y',  # Overwrite output files without asking
        '-i',
        rtsp_url,  # Input RTSP stream
        '-an',  # Disable audio
        '-vframes',
        '1',  # Capture only one frame
        '-f',
        'rawvideo',  # Output format: raw video
        '-pix_fmt',
        'bgr24',  # Pixel format: BGR 24-bit
        '-'  # Output to PIPE
    ]
    # Run FFmpeg command and capture the output
    process = subprocess.Popen(
        ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # read str from stderr
    try:
        out, err = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        msg = 'Timeout when reading the frame from the RTSP stream.'
        logger.error(msg)
        return None
    err_str = err.decode('utf-8')
    resolution_match = re.search(r', (\d+)x(\d+),', err_str)
    if resolution_match:
        # Get the resolution of the video stream
        width, height = resolution_match.groups()
        width, height = int(width), int(height)
    else:
        msg = 'Failed to get the resolution of the video stream.'
        logger.error(msg)
        return None
    # Read the output from stdout
    raw_frame = out
    # Convert the raw frame data to a numpy array
    frame_array = np.frombuffer(raw_frame, dtype=np.uint8)
    try:
        frame = frame_array.reshape((height, width, 3))
    except ValueError:
        msg = 'Failed to reshape the frame data to an image.'
        logger.error(msg)
        return None
    # Check if the FFmpeg process has finished
    if process.poll() is not None:
        pass
    else:
        process.kill()
    return frame
