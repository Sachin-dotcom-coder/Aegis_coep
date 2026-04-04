import cv2
import numpy as np

class SceneCutDetector:
    """
    Detects abrupt clip transitions in compiled CCTV videos.
    When a cut is detected, signals all other detectors to reset.
    """
    CUT_THRESHOLD = 60.0   # very high mean diff = new clip, not crash
    
    def __init__(self):
        self._prev_gray = None
    
    def is_scene_cut(self, frame: np.ndarray) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is None:
            self._prev_gray = gray
            return False
        
        diff     = cv2.absdiff(gray, self._prev_gray).astype(np.float32)
        mean_diff = float(np.mean(diff))
        self._prev_gray = gray
        
        return mean_diff > self.CUT_THRESHOLD
