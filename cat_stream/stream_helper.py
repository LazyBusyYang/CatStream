import logging
import time
from typing import Union

from .detection import build_detection
from .obs_client import ObsClient
from .rtsp_reader import read_img_from_rtsp_cv2, read_img_from_rtsp_ffmpeg


class StreamHelper:

    def __init__(self,
                 obs_ws_url: str,
                 obs_ws_pwd: str,
                 cat_det_cfg: dict,
                 rtsp_reader_backend: str,
                 obs_scenes: dict,
                 detect_interval: int = 10,
                 missing_tolerance: int = 3,
                 logger: Union[None, str, logging.Logger] = None) -> None:
        """A helper class for controlling the live scene in OBS according to
        the cat detection result from the RTSP stream.

        Args:
            obs_ws_url (str):
                The url of the OBS websocket.
            obs_ws_pwd (str):
                The password of the OBS websocket.
            cat_det_cfg (dict):
                The configuration of the cat detection model.
            rtsp_reader_backend (str):
                The backend of the RTSP reader, either "cv2" or "ffmpeg".
            obs_scenes (dict):
                The scenes in OBS, whose keys are the scene names and
                values are the corresponding media source names.
            detect_interval (int, optional):
                The interval of detection in seconds. Defaults to 10.
            missing_tolerance (int, optional):
                The tolerance of missing cat detections. Defaults to 3.
            logger (Union[None, str, logging.Logger], optional):
                Logger for logging. If None, a logger
                named __name__ will be selected.
                Defaults to None.
        """
        # init logger
        if logger is None:
            self.logger = logging.getLogger(__name__)
        elif isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger
        # init obs ws client
        self.obs_client = ObsClient(
            ws_url=obs_ws_url, ws_pwd=obs_ws_pwd, logger=self.logger)
        if not self.obs_client.server_valid:
            raise ConnectionError('Failed to connect to the OBS server.')
        # init detection model
        self.detection = build_detection(cat_det_cfg)
        # choose rtsp reading function
        if rtsp_reader_backend == 'cv2':
            self.read_img_from_rtsp = read_img_from_rtsp_cv2
        elif rtsp_reader_backend == 'ffmpeg':
            self.read_img_from_rtsp = read_img_from_rtsp_ffmpeg
        else:
            raise ValueError('Invalid rtsp_reader_backend, ' +
                             'expected "cv2" or "ffmpeg", ' +
                             f'got {rtsp_reader_backend}.')
        # init simple attr
        self.detect_interval = detect_interval
        self.missing_tolerance = missing_tolerance
        self.obs_scenes = obs_scenes
        # init default scene
        self.default_scene_name = None
        first_scene_name = None
        for scene_name, scene_dict in obs_scenes.items():
            if first_scene_name is None:
                first_scene_name = scene_name
            if scene_dict.get('default', False):
                self.default_scene_name = scene_name
                break
        if self.default_scene_name is None:
            self.default_scene_name = first_scene_name
        # init state attr
        self.current_scene_name = self.obs_client.get_current_scene_name()
        self.missing_count = 2

    def start(self) -> None:
        """Start the main loop of the stream helper."""
        while True:
            lasted_frames = dict()
            for scene_name, scene_dict in self.obs_scenes.items():
                src_name = scene_dict['media_source']
                src_settings = self.obs_client.get_source_settings(src_name)
                rtsp_url = src_settings['inputSettings']['input']
                img = self.read_img_from_rtsp(
                    rtsp_url=rtsp_url, logger=self.logger)
                if img is not None:
                    lasted_frames[scene_name] = img
                else:
                    msg = f'Failed to read frame from {scene_name}, ' +\
                        f'src_name: {src_name}, rtsp_url: {rtsp_url}.'
                    self.logger.warning(msg)
            cat_seen_scenes = list()
            for scene_name, frame in lasted_frames.items():
                detect_result = self.detection.detect(frame)
                if self.detection.check_cat(detect_result):
                    cat_seen_scenes.append(scene_name)
            if len(cat_seen_scenes) <= 0:
                self.missing_count += 1
                if self.missing_count >= self.missing_tolerance:
                    tgt_scene_name = self.default_scene_name
                    missing_count_tmp = self.missing_count
                    self.missing_count = 0
                    if self.current_scene_name != tgt_scene_name:
                        msg = f'Cat missing for {missing_count_tmp} times, ' +\
                            'switch to default scene ' +\
                            f'{self.default_scene_name}.'
                        self.logger.info(msg)
                        self.obs_client.set_current_scene(
                            self.default_scene_name)
                        self.current_scene_name = self.default_scene_name
            else:
                self.missing_count = 0
                tgt_scene_name = cat_seen_scenes[0]
                if self.current_scene_name != tgt_scene_name:
                    msg = f'Cat detected in {cat_seen_scenes}, ' +\
                        f'switch to scene {tgt_scene_name}.'
                    self.logger.info(msg)
                    self.obs_client.set_current_scene(tgt_scene_name)
                    self.current_scene_name = tgt_scene_name
            time.sleep(self.detect_interval)
