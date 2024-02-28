# import Abstract class
from abc import ABC
import numpy as np
from typing import Any
import cv2
try:
    import torch
    has_torch = True
except ImportError:
    has_torch = False

class BaseCatDetection(ABC):
    def __init__(self) -> None:
        pass

    def detect(self, frame: np.ndarray) -> Any:
        pass

    def check_cat(self, detect_result: Any) -> bool:
        pass


class OpenCVCatFaceDetection(BaseCatDetection):
    """A cat face detection class using OpenCV,
    only for poor machines as cat butt detection is not supported.
    """
    def __init__(self) -> None:
        super().__init__()

    def detect(self, frame: np.ndarray) -> list:
        cat_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalcatface.xml')
        gray_image = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # TODO: tune the parameters if needed
        cat_faces = cat_cascade.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        return cat_faces

    def check_cat(self, detect_result: Any) -> bool:
        if len(detect_result) > 0:
            return True
        else:
            return False


class YOLOv5CatDetection(BaseCatDetection):
    """A cat detection class using YOLOv5.
    """

    def __init__(self, device: str = 'cpu') -> None:
        super().__init__()
        if not has_torch:
            raise ImportError('PyTorch is not installed.')
        # TODO: Load locally if needed
        self.device = device
        self.model = torch.hub.load(
            'ultralytics/yolov5',
            'yolov5s',
            pretrained=True).to(self.device)

    def detect(self, frame: np.ndarray) -> Any:
        results = self.model(frame)
        return results

    def check_cat(self, detect_result: Any) -> bool:
        return 'cat' in str(detect_result)


def build_detection(cfg: dict) -> BaseCatDetection:
    cfg = cfg.copy()
    class_name = cfg.pop('type')
    if class_name == 'OpenCVCatFaceDetection':
        detection = OpenCVCatFaceDetection(**cfg)
    elif class_name == 'YOLOv5CatDetection':
        detection = YOLOv5CatDetection(**cfg)
    else:
        raise TypeError(f'Invalid type {class_name}.')
    return detection
        