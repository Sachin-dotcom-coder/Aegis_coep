"""
confidence.py — Phase 4
Combines raw YOLO detection confidence with zone reliability
and crowd anomaly scores to produce a final `detect_confidence` value.

Also runs the IsolationForest anomaly detector on bounding-box velocities.
"""

import numpy as np
from sklearn.ensemble import IsolationForest


# ---------------------------------------------------------------------------
# Confidence blending
# ---------------------------------------------------------------------------

def blend_confidence(
    yolo_conf: float,
    zone_accident_frequency: float,
    anomaly_score: float = 0.0
) -> float:
    """
    Blend three signals into a single detect_confidence [0, 1].

    Weights:
        50% raw YOLO confidence
        30% zone accident frequency (hotter zone → higher confidence)
        20% anomaly score (crowd misbehaviour boosts confidence) basically tells how abnormal the crowd pattern is 
    """
    blended = (
        0.50 * yolo_conf +
        0.30 * zone_accident_frequency +
        0.20 * anomaly_score
    )
    return round(min(max(blended, 0.0), 1.0), 3) #Returns the confidence rating 


# ---------------------------------------------------------------------------
# IsolationForest anomaly detector
# ---------------------------------------------------------------------------

class CrowdAnomalyDetector:
    """
    Detects unusual crowd movement using an IsolationForest model.

    Input: a list of per-person velocity vectors [vx, vy] for each frame.
    Output: anomaly score in [0, 1] (1 = very anomalous).
    """

    def __init__(self, warm_up_frames: int = 30, contamination: float = 0.1):
        self.warm_up_frames = warm_up_frames
        self.contamination = contamination
        self._model = IsolationForest(
            n_estimators=100,
            contamination=contamination,
            random_state=42,
        )
        self._history: list[list[float]] = []   # list of [vx, vy, density]
        self._fitted = False

    def update(self, velocities: list[tuple[float, float]], density: float) -> float:
        """
        Call once per frame with a list of (vx, vy) for each detected person.
        Returns an anomaly score in [0, 1].
        """
        if not velocities:
            return 0.0

        # Feature: mean velocity magnitude + density
        magnitudes = [np.sqrt(vx**2 + vy**2) for vx, vy in velocities]
        mean_vel = float(np.mean(magnitudes))
        max_vel  = float(np.max(magnitudes))
        feature  = [mean_vel, max_vel, density]

        self._history.append(feature)

        # Fit/refit once we have enough history
        if len(self._history) >= self.warm_up_frames:
            X = np.array(self._history[-200:])   # rolling 200-frame window
            self._model.fit(X)
            self._fitted = True

        if not self._fitted:
            return 0.0

        score = self._model.score_samples([feature])[0]   # more negative = more anomalous
        # Normalise to [0, 1]: IsolationForest scores ~ [-0.5, 0.5]
        normalised = float(np.clip((score * -1 + 0.5), 0.0, 1.0))
        return round(normalised, 3)
