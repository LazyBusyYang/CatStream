# import Abstract class
import cv2
import numpy as np
from abc import ABC
from typing import Any

try:
    import torch
    has_torch = True
except ImportError:
    has_torch = False


class BaseCatDetection(ABC):
    """Base class for cat detection."""

    def __init__(self) -> None:
        """Initialize the cat detection class."""
        pass

    def detect(self, frame: np.ndarray) -> Any:
        """Detect the cat in the cv2 RGB frame."""
        pass

    def check_cat(self, detect_result: Any) -> bool:
        """Check if the cat is detected in the detection result."""
        pass


class OpenCVCatFaceDetection(BaseCatDetection):
    """A cat face detection class using OpenCV, only for poor machines as cat
    butt detection is not supported."""

    def __init__(self) -> None:
        """Initialize the cat face detection class."""
        super().__init__()

    def detect(self, frame: np.ndarray) -> list:
        """Detect the cat face in the cv2 RGB frame.

        Args:
            frame (np.ndarray): The RGB frame.

        Returns:
            list: A list of detected cat faces, where each cat face is a tuple
                of (x, y, w, h).
        """
        cat_cascade = cv2.CascadeClassifier(cv2.data.haarcascades +
                                            'haarcascade_frontalcatface.xml')
        gray_image = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # TODO: tune the parameters if needed
        cat_faces = cat_cascade.detectMultiScale(
            gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        return cat_faces

    def check_cat(self, detect_result: Any) -> bool:
        """Check if the cat is detected in the detection result.

        Args:
            detect_result (Any):
                Result from the detect method.

        Returns:
            bool: True if the cat is detected, otherwise False.
        """
        if len(detect_result) > 0:
            return True
        else:
            return False


class YOLOv5CatDetection(BaseCatDetection):
    """A cat detection class using YOLOv5."""

    def __init__(self, device: str = 'cpu') -> None:
        """
        Args:
            device (str, optional):
                The device to run the model, 'cpu' or 'cuda:0' etc.
                Defaults to 'cpu'.

        Raises:
            ImportError: PyTorch is not installed.
        """
        super().__init__()
        if not has_torch:
            raise ImportError('PyTorch is not installed.')
        # TODO: Load locally if needed
        self.device = device
        self.model = torch.hub.load(
            'ultralytics/yolov5', 'yolov5s', pretrained=True).to(self.device)

    def detect(self, frame: np.ndarray) -> Any:
        """Detect the cat in the cv2 RGB frame.

        Args:
            frame (np.ndarray):
                The RGB frame.

        Returns:
            Any: The detection result.
        """
        results = self.model(frame)
        return results

    def check_cat(self, detect_result: Any) -> bool:
        """Check if the cat is detected in the detection result.

        Args:
            detect_result (Any):
                The detection result.

        Returns:
            bool:
                True if the cat is detected, otherwise False.
        """
        return 'cat' in str(detect_result)


def build_detection(cfg: dict) -> BaseCatDetection:
    """Build a cat detection object from the configuration.

    Args:
        cfg (dict):
            Configuration for building a cat detection object.

    Raises:
        TypeError:
            Invalid type.

    Returns:
        BaseCatDetection:
            A cat detection object.
    """
    cfg = cfg.copy()
    class_name = cfg.pop('type')
    if class_name == 'OpenCVCatFaceDetection':
        detection = OpenCVCatFaceDetection(**cfg)
    elif class_name == 'YOLOv5CatDetection':
        detection = YOLOv5CatDetection(**cfg)
    else:
        raise TypeError(f'Invalid type {class_name}.')
    return detection
