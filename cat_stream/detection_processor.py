import cv2
import logging
from queue import Empty, Queue
from threading import Event, Thread
from typing import Union

from .detection import build_detection
from .mthread_utils import force_put
from .rtsp_reader import read_img_from_rtsp_cv2, read_img_from_rtsp_ffmpeg


class DetectionProcessor:
    """A class for processing detection requests, putting them into a detection
    thread, and getting the detection results."""

    def __init__(self,
                 detect_thread_cfg: dict,
                 verbose: bool = False,
                 input_queue_len: int = 1,
                 output_queue_len: int = 1,
                 logger: Union[None, str, logging.Logger] = None) -> None:
        """
        Args:
            detect_thread_cfg (dict):
                Configuration for building a detection thread.
            verbose (bool, optional):
                Whether to print detailed log messages.
                Defaults to False.
            input_queue_len (int, optional):
                Length of the input queue.
                Defaults to 1.
            output_queue_len (int, optional):
                Length of the output queue.
                Defaults to 1.
            logger (Union[None, str, logging.Logger], optional):
                Logger for logging. If None, a logger
                named __name__ will be selected.
                Defaults to None.
        """
        if logger is None:
            self.logger = logging.getLogger(__name__)
        elif isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger
        self.input_queue_len = input_queue_len
        self.input_queue = Queue(maxsize=input_queue_len)
        self.output_queue_len = output_queue_len
        self.output_queue = Queue(maxsize=output_queue_len)
        self.exit_signal = Event()
        class_name = detect_thread_cfg.pop('type')
        if class_name != 'RTSPDetectionThread':
            raise TypeError('Invalid type of detect_thread, ' +
                            'expected RTSPDetectionThread, ' +
                            f'got {class_name}.')
        detect_thread_cfg['input_queue'] = self.input_queue
        detect_thread_cfg['output_queue'] = self.output_queue
        detect_thread_cfg['exit_signal'] = self.exit_signal
        detect_thread_cfg['logger'] = self.logger
        self.verbose = verbose
        self.worker_thread = RTSPDetectionThread(**detect_thread_cfg)
        self.worker_thread.start()

    def put_mview_urls(self, rtsp_urls: dict) -> None:
        """Put RTSP URLs into the input queue.

        Args:
            rtsp_urls (dict):
                A dictionary of RTSP URLs, where the key is the
                name of the RTSP stream, and the value is a tuple
                of the RTSP URL and the rotation of the RTSP stream.
        """
        # ensure the queue is not full
        force_put(self.input_queue, rtsp_urls)

    def get_mview_results(self) -> Union[dict, None]:
        """Get detection results from the output queue.

        Returns:
            Union[dict, None]:
                A dictionary of detection results, where the key
                is the name of the RTSP stream, and the value is
                a boolean indicating whether a cat is detected.
                If the output queue is empty, return None.
        """
        try:
            return self.output_queue.get_nowait()
        except Empty:
            return None

    def stop_thread(self) -> None:
        """Stop the detection thread."""
        self.exit_signal.set()
        if self.verbose:
            self.logger.info('[DetectionProcessor] Stop signal is sent to ' +
                             'the detection thread.')
        self.worker_thread.join()
        self.logger.info('[DetectionProcessor] Processor and its ' +
                         'detection thread have been stopped.')


class StopLoop(Exception):
    pass


class RTSPDetectionThread(Thread):
    """A thread for detecting cats from RTSP streams."""

    def __init__(self,
                 input_queue: Queue,
                 output_queue: Queue,
                 exit_signal: Event,
                 cat_det_cfg: dict,
                 rtsp_reader_backend: str = 'ffmpeg',
                 rtsp_timeout: int = 5,
                 rtsp_tolerance: int = 5,
                 interval: int = 1,
                 verbose: bool = False,
                 logger: Union[None, str, logging.Logger] = None) -> None:
        """
        Args:
            input_queue (Queue):
                A queue for receiving detect request (RTSP URLs).
            output_queue (Queue):
                A queue for sending detection results.
            exit_signal (Event):
                An event for stopping the thread.
            cat_det_cfg (dict):
                Configuration for building a cat detection object.
            rtsp_reader_backend (str, optional):
                The backend for reading RTSP streams.
                Defaults to 'ffmpeg'.
            rtsp_timeout (int, optional):
                The timeout for reading RTSP streams.
                Defaults to 5(sec).
            rtsp_tolerance (int, optional):
                The tolerance for failing to read RTSP streams.
                Defaults to 5(sec).
            interval (int, optional):
                The interval for checking the input queue.
                Defaults to 1(sec).
            verbose (bool, optional):
                Whether to print detailed log messages.
                Defaults to False.
            logger (Union[None, str, logging.Logger], optional):
                Logger for logging. If None, a logger
                named __name__ will be selected.
                Defaults to None.
        """
        super().__init__()
        if logger is None:
            self.logger = logging.getLogger(__name__)
        elif isinstance(logger, str):
            self.logger = logging.getLogger(logger)
        else:
            self.logger = logger
        # choose rtsp reading function
        if rtsp_reader_backend == 'cv2':
            self.read_img_from_rtsp = read_img_from_rtsp_cv2
        elif rtsp_reader_backend == 'ffmpeg':
            self.read_img_from_rtsp = read_img_from_rtsp_ffmpeg
        self.interval = interval
        self.rtsp_timeout = rtsp_timeout
        self.rtsp_tolerance = rtsp_tolerance
        self.rtsp_failure_count = dict()
        self.rtsp_backlist = list()
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.exit_signal = exit_signal
        self.cat_detection = build_detection(cat_det_cfg)
        self.verbose = verbose
        self.logger.info(
            '[RTSPDetectionThread] Initialized RTSPDetectionThread.')

    def _run_one_loop(self) -> None:
        # check signal first
        try:
            if self.exit_signal.is_set():
                raise StopLoop
        except Exception as e:
            if self.verbose:
                self.logger.info('[RTSPDetectionThread] Exception caught, ' +
                                 f'class={e.__class__}.')
            raise StopLoop
        try:
            rtsp_urls = self.input_queue.get(timeout=self.interval)
        except Empty:
            return
        mview_results = dict()
        for rtsp_key, rtsp_tuple in rtsp_urls.items():
            rtsp_url = rtsp_tuple[0]
            rtsp_rotation = rtsp_tuple[1]
            if rtsp_key in self.rtsp_backlist:
                continue
            if rtsp_key not in self.rtsp_failure_count:
                self.rtsp_failure_count[rtsp_key] = 0
            frame = self.read_img_from_rtsp(
                rtsp_url, timeout=self.rtsp_timeout, logger=self.logger)
            if frame is None:
                self.rtsp_failure_count[rtsp_key] += 1
                self.logger.warning('[RTSPDetectionThread] Failed to ' +
                                    f'read frame from {rtsp_key} {rtsp_url}.')
                if self.rtsp_failure_count[rtsp_key] >= self.rtsp_tolerance:
                    self.rtsp_backlist.append(rtsp_key)
                    self.logger.warning(
                        '[RTSPDetectionThread] ' +
                        f'{rtsp_key} {rtsp_url} is added to backlist.')
                continue
            # rotate the frame
            if rtsp_rotation == 180:
                frame = cv2.rotate(src=frame, rotateCode=cv2.ROTATE_180)
            detect_result = self.cat_detection.detect(frame)
            cat_seen = self.cat_detection.check_cat(detect_result)
            mview_results[rtsp_key] = cat_seen
        if self.verbose:
            self.logger.info('[RTSPDetectionThread] Detection results: ' +
                             f'{mview_results}.')
        force_put(self.output_queue, mview_results)

    def run(self) -> None:
        while True:
            try:
                self._run_one_loop()
            except StopLoop:
                self.logger.info('[RTSPDetectionThread] ' +
                                 'Thread is interrupted by user.')
                break
