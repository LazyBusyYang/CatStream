import logging
import time
from enum import Enum, auto
from typing import Tuple, Union

from .bili_interact_reader import BiliInteractReader
from .detection import build_detection
from .obs_client import ObsClient
from .rtsp_reader import read_img_from_rtsp_cv2, read_img_from_rtsp_ffmpeg


class State(Enum):
    INITIAL = auto()
    ACTIVE = auto()
    IDLE = auto()
    LOCKED = auto()


class StreamHelper:

    def __init__(self,
                 obs_ws_url: str,
                 obs_ws_pwd: str,
                 cat_det_cfg: dict,
                 rtsp_reader_backend: str,
                 obs_scenes: dict,
                 interact_reader_cfg: Union[dict, None],
                 mainloop_interval: int = 1,
                 vote_interval: int = 10,
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
            interact_reader_cfg (Union[dict, None]):
                The configuration of the interact reader.
                If None, the interact reader will not be used.
            mainloop_interval (int, optional):
                The interval of the main loop in seconds. Defaults to 1.
            vote_interval (int, optional):
                The interval of vote detection in seconds. Defaults to 10.
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
        # init comment reader
        if interact_reader_cfg is not None:
            class_name = interact_reader_cfg.pop('type')
            if class_name != 'BiliInteractReader':
                raise TypeError('Invalid type of comment reader, ' +
                                'expected BiliInteractReader, ' +
                                f'got {class_name}.')
            self.interact_reader = BiliInteractReader(**interact_reader_cfg)
        else:
            self.interact_reader = None
        # init simple attr
        self.mainloop_interval = mainloop_interval
        self.vote_interval = vote_interval
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
        self.state = State.INITIAL
        self.missing_count = 0
        self.next_detect_time = 0.0

    def start(self) -> None:
        """Start the main loop of the stream helper."""
        self.logger.info('Start the main loop of the stream helper.')
        self.state = State.IDLE
        while True:
            loop_start_time = time.time()
            cat_seen_scenes = list()
            # not locked process detection
            if self.state != State.LOCKED and \
                    self.next_detect_time < loop_start_time:
                latest_frames = dict()
                for scene_name, scene_dict in self.obs_scenes.items():
                    src_name = scene_dict['media_source']
                    src_settings = self.obs_client.get_source_settings(
                        src_name)
                    rtsp_url = src_settings['inputSettings']['input']
                    img = self.read_img_from_rtsp(
                        rtsp_url=rtsp_url, logger=self.logger)
                    if img is not None:
                        latest_frames[scene_name] = img
                    else:
                        msg = f'Failed to read frame from {scene_name}, ' +\
                            f'src_name: {src_name}, rtsp_url: {rtsp_url}.'
                        self.logger.warning(msg)
                for scene_name, frame in latest_frames.items():
                    detect_result = self.detection.detect(frame)
                    if self.detection.check_cat(detect_result):
                        cat_seen_scenes.append(scene_name)
                self.next_detect_time = loop_start_time + self.detect_interval
            # state transition
            if self.state == State.IDLE:
                if len(cat_seen_scenes) > 0:
                    self.state = State.ACTIVE
                    msg = '[State] IDLE to ACTIVE'
                    self.logger.info(msg)
                    self.missing_count = 0
                    tgt_scene_name = cat_seen_scenes[0]
                    current_scene_name = \
                        self.obs_client.get_current_scene_name()
                    if current_scene_name != tgt_scene_name:
                        msg = f'Cat detected in {cat_seen_scenes}, ' +\
                            f'switch to scene {tgt_scene_name}.'
                        self.logger.info(msg)
                        self.obs_client.set_current_scene(tgt_scene_name)
                else:
                    # control the scene by the comment reader
                    if self.interact_reader is not None:
                        vote_results = self.interact_reader.get_vote_results()
                        label_text, tgt_scene_name = \
                            self._convert_vote_results(vote_results)
                        time_left = self.next_vote_time - loop_start_time
                        if time_left <= 0:
                            self.next_vote_time = \
                                loop_start_time + self.vote_interval
                            if tgt_scene_name is not None:
                                msg = f'Switch to scene {tgt_scene_name} ' +\
                                    'according to the vote results.'
                                self.logger.info(msg)
                                self.obs_client.set_current_scene(
                                    tgt_scene_name)
                            time_left = self.vote_interval
                        label_text = f'{label_text}\n' +\
                            f'距离下次切换视角还有{time_left:.1f}秒'
                        current_scene_name = \
                            self.obs_client.get_current_scene_name()
                        self._set_state_label(current_scene_name, label_text)
            elif self.state == State.ACTIVE:
                if len(cat_seen_scenes) <= 0:
                    self.missing_count += 1
                else:
                    self.missing_count = 0
                if self.missing_count >= self.missing_tolerance:
                    self._transit_to_idle()
                    tgt_scene_name = self.default_scene_name
                    current_scene_name = \
                        self.obs_client.get_current_scene_name()
                    if current_scene_name != tgt_scene_name:
                        msg = 'Cat missing for ' +\
                            f'{self.missing_count} times, ' +\
                            'switch to default scene ' +\
                            f'{self.default_scene_name}.'
                        self.logger.info(msg)
                        self.obs_client.set_current_scene(
                            self.default_scene_name)
            elif self.state == State.LOCKED:
                raise NotImplementedError
            else:
                msg = f'Invalid state {self.state} in main loop.'
                self.logger.warning(msg)
                self._transit_to_idle()
            # sleep until time for the next loop
            loop_end_time = time.time()
            time_to_sleep = self.mainloop_interval - \
                (loop_end_time - loop_start_time)
            actual_sleep = max(0.5, time_to_sleep)
            time.sleep(actual_sleep)

    def _transit_to_idle(self) -> None:
        msg = f'[State] {self.state} to IDLE'
        if self.interact_reader is not None:
            self.interact_reader.reset()
        self.state = State.IDLE
        self.logger.info(msg)
        self.next_vote_time = time.time() + self.vote_interval

    def _convert_vote_results(self, vote_results: dict) -> Tuple[str, str]:
        vote_by_scene = dict()
        max_vote_number = -1
        max_vote_scene_name = None
        for scene_name, vote_key in self.obs_scenes.items():
            n_votes = vote_results[vote_key] \
                if vote_key in vote_results else 0
            vote_by_scene[scene_name] = n_votes
            if n_votes > max_vote_number:
                max_vote_number = n_votes
                max_vote_scene_name = scene_name
        if max_vote_number == 0:
            max_vote_scene_name = None
        lable_text = ''
        for scene_name, n_votes in vote_by_scene.items():
            lable_text += f'{scene_name} 票数: {n_votes}\n'
        return lable_text, max_vote_scene_name

    def _set_state_label(self, scene_name: str, detailed_text: str) -> None:
        src_name = self.obs_scenes[scene_name]['state_label_source']
        if self.state == State.ACTIVE:
            state_text = '检测到猫咪，弹幕控制不可用'
        elif self.state == State.IDLE:
            state_text = '未检测到猫咪，弹幕控制可用'
        elif self.state == State.LOCKED:
            state_text = '视角已锁定'
        else:
            state_text = '未知状态'
        text = f'{state_text}\n{detailed_text}'
        self.obs_client.set_source_text(src_name, text)
