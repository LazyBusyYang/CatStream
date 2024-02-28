import asyncio
import cv2
import datetime
import logging
import numpy as np
import re
import simpleobsws
import subprocess
import time
import torch
from typing import Union


class Client:

    def __init__(self,
                 ws_url: str,
                 ws_pwd: str,
                 logger: Union[None, str, logging.Logger] = None) -> None:
        """A client for controlling the live scene in OBS.

        Args:
            ws_url (str):
                The url of the OBS websocket.
            ws_pwd (str):
                The password of the OBS websocket.
            logger (Union[None, str, logging.Logger], optional):
                Logger for logging. If None, root logger will be selected.
                Defaults to None.
        """
        if logger is None:
            logger = logging.getLogger(__name__)
        elif isinstance(logger, str):
            logger = logging.getLogger(logger)
        self.logger = logger
        self.ws_url = ws_url
        self.ws_pwd = ws_pwd
        # Create an IdentificationParameters object (optional for connecting)
        identification_parameters = simpleobsws.IdentificationParameters(
            ignoreNonFatalRequestChecks=False)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        self.loop = loop

        # connect to obs
        self.ws = simpleobsws.WebSocketClient(
            url=ws_url,
            password=ws_pwd,
            identification_parameters=identification_parameters,
        )

    @property
    def server_valid(self) -> bool:
        try:
            self.loop.run_until_complete(self.ws.connect())
            self.loop.run_until_complete(self.ws.wait_until_identified())
        except Exception as e:
            self.logger.error(e)
            return False
        self.loop.run_until_complete(self.ws.disconnect())
        return True

    def __del__(self) -> None:
        self.loop.close()

    def set_current_scene(self, scene_name: str) -> None:
        """Switch to a product by its name.

        Args:
            product_name (str):
                The name of the product to switch to.
        """
        self.loop.run_until_complete(
            set_current_scene(self.ws, scene_name, self.logger))

    def get_source_settings(self, source_name: str) -> dict:
        """Get settings of a source.

        Args:
            source_name (str):
                The name of the source.
        Returns:
            dict: The settings of the source.
        """
        return self.loop.run_until_complete(
            get_source_settings(self.ws, source_name, self.logger))

    def get_current_scene_name(self) -> str:
        """Get name of the current scene.

        Returns:
            str:
                The name of the current scene.
        """
        return self.loop.run_until_complete(
            get_current_scene_name(self.ws, self.logger))


async def set_current_scene(
    ws: simpleobsws.WebSocketClient,
    scene_name: str,
    logger: Union[None, str, logging.Logger] = None,
):
    """Set the current scene by scene name.

    Args:
        ws (simpleobsws.WebSocketClient):
            The websocket client.
        scene_name (str):
            The name of the scene.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.
    Raises:
        RuntimeError:
            If the request failed.
    """
    # connect and authenticate
    await ws.connect()
    await ws.wait_until_identified()
    request = simpleobsws.Request(
        requestType='SetCurrentProgramScene',
        requestData=dict(sceneName=scene_name))
    ret = await ws.call(request)
    if not ret.ok():
        logger.error('Failed to set the current visible scene.\n' +
                     f'Error code: {ret.requestStatus.code}\n' +
                     f'Error message: {ret.requestStatus.comment}')
        raise RuntimeError(ret.requestStatus.comment)
    await ws.disconnect()
    return


async def get_current_scene_name(
        ws: simpleobsws.WebSocketClient,
        logger: Union[None, str, logging.Logger] = None) -> str:
    """Get name of the current scene.

    Args:
        ws (simpleobsws.WebSocketClient):
            The websocket client.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.
    Returns:
        str:
            The name of the current scene.
    Raises:
        RuntimeError:
            If the request failed.
    """
    # connect and authenticate
    await ws.connect()
    await ws.wait_until_identified()
    request = simpleobsws.Request(requestType='GetCurrentProgramScene')
    ret = await ws.call(request)
    if ret.ok():
        scene_name = ret.responseData['currentProgramSceneName']
    else:
        logger.error('Failed to get name of the current scene.\n' +
                     f'Error code: {ret.requestStatus.code}\n' +
                     f'Error message: {ret.requestStatus.comment}')
        raise RuntimeError(ret.requestStatus.comment)
    await ws.disconnect()
    return scene_name


async def get_source_settings(
    ws: simpleobsws.WebSocketClient,
    source_name: str,
    logger: Union[None, str, logging.Logger] = None,
) -> dict:
    """Get settings of a source.

    Args:
        ws (simpleobsws.WebSocketClient):
            The websocket client.
        source_name (str):
            The name of the source.
        logger (Union[None, str, logging.Logger], optional):
            Logger for logging. If None, root logger will be selected.
            Defaults to None.
    Returns:
        dict: The settings of the source.
    Raises:
        RuntimeError:
            If the request failed.
    """
    # connect and authenticate
    await ws.connect()
    await ws.wait_until_identified()
    request = simpleobsws.Request(
        requestType='GetInputSettings',
        requestData=dict(inputName=source_name))
    ret = await ws.call(request)
    if ret.ok():
        type_setting_dict = ret.responseData
    else:
        logger.error(f'Failed to get source settings of {source_name}.\n' +
                     f'Error code: {ret.requestStatus.code}\n' +
                     f'Error message: {ret.requestStatus.comment}')
        raise RuntimeError(ret.requestStatus.comment)
    await ws.disconnect()
    return type_setting_dict


def get_img_from_rtsp_cv2(rtsp_url: str) -> np.ndarray:
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        print('无法打开视频流')
        return None
    ret, frame = cap.read()
    if ret:
        return frame
    else:
        return None


def get_img_from_rtsp_ffmpeg(rtsp_url: str) -> Union[np.ndarray, None]:
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
    out, err = process.communicate()
    err_str = err.decode('utf-8')
    resolution_match = re.search(r', (\d+)x(\d+),', err_str)
    if resolution_match:
        # 提取分辨率的宽度和高度
        width, height = resolution_match.groups()
        width, height = int(width), int(height)
    else:
        raise ValueError('无法获取视频流分辨率')
    # Read the output from the PIPE
    raw_frame = out
    # Convert the raw frame data to a numpy array
    frame_array = np.frombuffer(raw_frame, dtype=np.uint8)
    frame = frame_array.reshape((height, width, 3))
    # Check if the FFmpeg process has finished
    if process.poll() is not None:
        pass
    else:
        process.kill()
    return frame


def detect_cat_face(image: np.ndarray) -> bool:
    cat_cascade = cv2.CascadeClassifier(cv2.data.haarcascades +
                                        'haarcascade_frontalcatface.xml')
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cat_faces = cat_cascade.detectMultiScale(
        gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(cat_faces) > 0:
        return True
    else:
        return False


def detect_cat_yolo(image: np.ndarray) -> bool:
    cat_cascade = cv2.CascadeClassifier(cv2.data.haarcascades +
                                        'haarcascade_frontalcatface.xml')
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cat_faces = cat_cascade.detectMultiScale(
        gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    if len(cat_faces) > 0:
        return True
    else:
        return False


def main():
    obs_host = '192.168.111.111'
    obs_ws_port = 4455
    obs_pwd = 'qqdIciF8FPNfzrqX'
    ws_url = f'ws://{obs_host}:{obs_ws_port}'
    live_client = Client(ws_url=ws_url, ws_pwd=obs_pwd)
    scene_source_mapping = dict(balcony='Mi8SE', kitchen='Redmi4')
    default_scene = 'balcony'
    check_interval = 10
    model = torch.hub.load('ultralytics/yolov5', 'yolov5s')
    while True:
        ret_img = dict()
        for scene_name, src_name in scene_source_mapping.items():
            src_settings = live_client.get_source_settings(src_name)
            rtsp_url = src_settings['inputSettings']['input']
            img = get_img_from_rtsp_ffmpeg(rtsp_url)
            ret_img[scene_name] = img
        # detect cat
        cat_det = dict()
        cat_found = False
        for scene_name, img in ret_img.items():
            if img is not None:
                results = model(img)
                cat_seen = 'cat' in str(results)
                cat_det[scene_name] = cat_seen
                # results.show()
                if cat_seen:
                    cat_found = True
                    break
            else:
                cat_det[scene_name] = False
        # # imshow
        # for scene_name, img in ret_img.items():
        #     cv2.imshow(scene_name, img)
        #     cv2.waitKey(0)
        # set scene
        if not cat_found:
            next_scene = default_scene
            msg = f'No cat found, switch to default scene {default_scene}.'
        else:
            for scene_name, cat_seen in cat_det.items():
                if cat_seen:
                    next_scene = scene_name
                    msg = f'Cat found in {scene_name}, switch to {scene_name}.'
                    break
        last_scene = live_client.get_current_scene_name()
        if last_scene is None or next_scene != last_scene:
            live_client.set_current_scene(next_scene)
            datetime_str = datetime.datetime.now().strftime(
                '%Y-%m-%d %H:%M:%S')
            print(f'{datetime_str} Switch to {next_scene}. {msg}')
            last_scene = next_scene
        time.sleep(check_interval)


if __name__ == '__main__':
    main()
