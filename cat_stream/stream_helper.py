import logging
import prettytable
import time
from enum import Enum, auto
from typing import Tuple, Union

from .bili_interact_reader import BiliInteractReader
from .detection_processor import DetectionProcessor
from .obs_client import ObsClient


class State(Enum):
    INITIAL = auto()
    IDLE = auto()
    EXIT = auto()


class StreamHelper:

    def __init__(self,
                 obs_ws_url: str,
                 obs_ws_pwd: str,
                 obs_scenes: dict,
                 detection_proc_cfg: Union[dict, None] = None,
                 interact_reader_cfg: Union[dict, None] = None,
                 mainloop_interval: int = 1,
                 vote_interval: int = 10,
                 detect_interval: int = 10,
                 logger: Union[None, str, logging.Logger] = None) -> None:
        """A helper class for controlling the live scene in OBS according to
        the cat detection result or interactive vote result.

        Args:
            obs_ws_url (str):
                The url of the OBS websocket.
            obs_ws_pwd (str):
                The password of the OBS websocket.
            obs_scenes (dict):
                The scenes in OBS, whose keys are the scene names and
                values are corresponding media source names, transformations,
                and vote keys.
            detection_proc_cfg (Union[dict, None]):
                The configuration of the detection processor.
                If None, the detection processor will not be used.
            interact_reader_cfg (Union[dict, None]):
                The configuration of the interact reader.
                If None, the interact reader will not be used.
            mainloop_interval (int, optional):
                The interval of the main loop in seconds. Defaults to 1.
            vote_interval (int, optional):
                The interval of vote detection in seconds. Defaults to 10.
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
        # init detection processor
        if detection_proc_cfg is not None:
            class_name = detection_proc_cfg.pop('type')
            if class_name != 'DetectionProcessor':
                raise TypeError('Invalid type of detection reader, ' +
                                'expected DetectionProcessor, ' +
                                f'got {class_name}.')
            detection_proc_cfg['logger'] = self.logger
            self.detection_processor = DetectionProcessor(**detection_proc_cfg)
        else:
            self.detection_processor = DetectionProcessor(logger=self.logger)
        # init interact reader
        if interact_reader_cfg is not None:
            class_name = interact_reader_cfg.pop('type')
            if class_name != 'BiliInteractReader':
                raise TypeError('Invalid type of comment reader, ' +
                                'expected BiliInteractReader, ' +
                                f'got {class_name}.')
            interact_reader_cfg['logger'] = self.logger
            self.interact_reader = BiliInteractReader(**interact_reader_cfg)
        else:
            self.interact_reader = None
        if self.detection_processor is None and self.interact_reader is None:
            msg = 'Both detection processor and interact reader are None, ' +\
                'the stream helper will not work.'
            self.logger.error(msg)
            raise ValueError(msg)
        # init simple attr
        self.mainloop_interval = mainloop_interval
        self.vote_interval = vote_interval
        self.detect_interval = detect_interval
        self.obs_scenes = obs_scenes
        # init obs scenes
        self.latest_scene_names = sorted(list(obs_scenes.keys()))
        self.offline_scene_names = list()
        self.vote_scene_mapping = dict()
        for scene_name, scene_dict in obs_scenes.items():
            vote_key = scene_dict['vote_key']
            self.vote_scene_mapping[vote_key] = scene_name
        # init state attr
        self.state = State.INITIAL
        self.last_detect_vote_results = None
        self.next_detect_time = 0.0
        current_scene_name = \
            self.obs_client.get_current_scene_name()
        self._set_state_label(scene_name=current_scene_name, detailed_text='')

    def _trigger_detection(self) -> None:
        rtsp_dict = dict()
        for scene_name, scene_dict in self.obs_scenes.items():
            src_name = scene_dict['media_source']
            src_settings = self.obs_client.get_source_settings(src_name)
            rtsp_url = src_settings['inputSettings']['input']
            rtsp_rotation = scene_dict.get('media_rotation', 0)
            rtsp_dict[scene_name] = (rtsp_url, rtsp_rotation)
        self.detection_processor.put_mview_urls(rtsp_dict)

    def _collect_detection_vote_results(self) -> dict:
        detect_results = self.detection_processor.get_mview_results()
        # check if the cat is seen
        if detect_results is not None:
            # update the latest scene names, some rtsp sources may be offline
            self.latest_scene_names = sorted(list(detect_results.keys()))
            # update the offline scene names
            self.offline_scene_names = [
                scene_name for scene_name in self.obs_scenes.keys()
                if scene_name not in self.latest_scene_names
            ]
            vote_results = dict()
            for scene_name, cat_seen in detect_results.items():
                if cat_seen:
                    vote_key = self.obs_scenes[scene_name]['vote_key']
                    vote_results[vote_key] = 3
            return vote_results
        else:
            return None

    def _run_one_loop(self):
        loop_start_time = time.time()
        vote_time_left = None
        if self.detection_processor is not None:
            # time to trigger detection
            if self.next_detect_time < loop_start_time:
                self._trigger_detection()
                self.next_detect_time = loop_start_time + self.detect_interval
            # always try to get detection results, None if not ready
            detect_vote_results = self._collect_detection_vote_results()
        else:
            detect_vote_results = None
        # always collect interact vote results
        if self.interact_reader is not None:
            interact_vote_results = self.interact_reader.get_vote_results()
        else:
            interact_vote_results = None
        # sum up the vote results and update obs text
        msrc_vote_results = dict()
        if interact_vote_results is not None:
            msrc_vote_results['弹幕'] = interact_vote_results
        if detect_vote_results is not None:
            msrc_vote_results['AI'] = detect_vote_results
            self.last_detect_vote_results = detect_vote_results
        elif self.last_detect_vote_results is not None:
            msrc_vote_results['AI'] = self.last_detect_vote_results
        label_text, tgt_scene_name = \
            self._convert_vote_results(msrc_vote_results)
        vote_time_left = self.next_vote_time - loop_start_time
        if vote_time_left <= 0:
            self.next_vote_time = \
                loop_start_time + self.vote_interval
            self.interact_reader.reset()
            if tgt_scene_name is not None:
                msg = f'[StreamHelper] Switch to scene {tgt_scene_name} ' +\
                    'according to the vote results.'
                self.logger.info(msg)
                self.obs_client.set_current_scene(tgt_scene_name)
                self.last_detect_vote_results = None
                label_text, _ = \
                    self._convert_vote_results(dict())
            vote_time_left = self.vote_interval
        label_text = f'弹幕控制可用\n{label_text}\n' +\
            f'距离下次切换视角还有{vote_time_left:.1f}秒'
        current_scene_name = \
            self.obs_client.get_current_scene_name()
        self._set_state_label(current_scene_name, label_text)
        # sleep until time for the next loop
        loop_end_time = time.time()
        time_to_sleep = self.mainloop_interval - \
            (loop_end_time - loop_start_time)
        actual_sleep = max(0.5, time_to_sleep)
        # shorten the sleep time if the vote time is closing
        if vote_time_left is not None and vote_time_left < 5:
            time_to_next_int = vote_time_left - int(vote_time_left)
            actual_sleep = min(time_to_next_int, actual_sleep)
        time.sleep(actual_sleep)

    def start(self) -> None:
        """Start the main loop of the stream helper."""
        self.logger.info(
            '[StreamHelper] Start the main loop of the stream helper.')
        self._transit_to_idle()
        while True:
            try:
                self._run_one_loop()
            except KeyboardInterrupt:
                self.logger.info(
                    '[StreamHelper] KeyboardInterrupt, stopping the main loop.'
                )
                self._transit_to_exit()
                self._set_state_label()
                self.detection_processor.stop_thread()
                if self.interact_reader is not None:
                    self.interact_reader.stop_thread()
                break

    def _transit_to_idle(self) -> None:
        msg = f'[State] {self.state} to IDLE'
        if self.interact_reader is not None:
            self.interact_reader.reset()
        self.state = State.IDLE
        self.logger.info(msg)
        self.next_vote_time = time.time() + self.vote_interval
        self._set_state_label()

    def _transit_to_exit(self) -> None:
        msg = f'[State] {self.state} to EXIT'
        self.state = State.EXIT
        self.logger.info(msg)
        self._set_state_label()

    def _convert_vote_results(self,
                              msrc_vote_results: dict) -> Tuple[str, str]:
        table = prettytable.PrettyTable()
        max_vote_number = 0
        max_vote_scene_name = None
        field_names = [
            '视角',
        ]
        for src_key in msrc_vote_results.keys():
            field_names.append(src_key)
        table.field_names = field_names
        vote_keys = sorted(list(self.vote_scene_mapping.keys()))
        for vote_key in vote_keys:
            scene_name = self.vote_scene_mapping[vote_key]
            if scene_name not in self.latest_scene_names:
                continue
            scene_cfg = self.obs_scenes[scene_name]
            vote_key = scene_cfg['vote_key']
            table_row = [
                vote_key,
            ]
            for src_key, vote_results in msrc_vote_results.items():
                if vote_key in vote_results:
                    vote_value = vote_results[vote_key]
                else:
                    vote_value = 0
                table_row.append(vote_value)
            table.add_row(table_row)
            vote_sum = sum(table_row[1:])
            if vote_sum > max_vote_number:
                max_vote_number = vote_sum
                max_vote_scene_name = scene_name
        lable_text = table.get_string() + '\n'
        for scene_name in self.offline_scene_names:
            vote_key = self.obs_scenes[scene_name]['vote_key']
            lable_text += f'{vote_key} 机位离线\n'
        return lable_text, max_vote_scene_name

    def _set_state_label(self,
                         scene_name: Union[str, None] = None,
                         detailed_text: Union[str, None] = None) -> None:
        scene_name = scene_name if scene_name is not None \
            else self.obs_client.get_current_scene_name()
        detailed_text = detailed_text if detailed_text is not None else ''
        src_name = self.obs_scenes[scene_name]['state_label_source']
        if self.state == State.IDLE:
            state_text = '控制程序运行中，欢迎投票'
        elif self.state == State.INITIAL:
            state_text = '初始化中'
        elif self.state == State.EXIT:
            state_text = '控制程序退出'
        else:
            state_text = '未知状态'
        text = f'{state_text}\n{detailed_text}'
        self.obs_client.set_source_text(src_name, text)
