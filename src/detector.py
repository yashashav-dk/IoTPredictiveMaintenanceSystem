"""Anomaly detection engine for IoT sensor data.

Uses Modified Z-Score (based on Median Absolute Deviation) to identify
anomalous readings in vibration and temperature sensor streams. MAD-based
scoring is more robust to outliers than standard deviation, making it
well-suited for noisy industrial sensor data.
"""

import numpy as np


class AnomalyDetector:
    """Detects anomalies in sensor readings using the Modified Z-Score method.

    The Modified Z-Score replaces the mean with the median and the standard
    deviation with the Median Absolute Deviation (MAD), making the statistic
    resistant to the very outliers it is trying to detect.

    Formula:
        MAD = median(|xi - median(X)|)
        Modified Z-Score = 0.6745 * (xi - median(X)) / MAD

    The constant 0.6745 is the 0.75th quartile of the standard normal
    distribution, which makes the MAD a consistent estimator for sigma.

    Args:
        threshold: Modified Z-Score above which a reading is flagged.
                   Default of 3.5 is a widely-used conservative choice.
    """

    CONSISTENCY_CONSTANT = 0.6745

    def __init__(self, threshold: float = 3.5):
        if threshold <= 0:
            raise ValueError("Threshold must be a positive number")
        self.threshold = threshold

    def _modified_z_scores(self, data: np.ndarray) -> np.ndarray:
        """Compute Modified Z-Scores for a 1-D array."""
        median = np.median(data)
        mad = np.median(np.abs(data - median))

        if mad == 0:
            # All values identical (or nearly so) — fall back to mean-based
            # z-score so we can still flag a single spike injected into
            # constant data.
            std = np.std(data)
            if std == 0:
                return np.zeros_like(data, dtype=float)
            return np.abs(data - np.mean(data)) / std

        return np.abs(self.CONSISTENCY_CONSTANT * (data - median) / mad)

    def detect(self, readings: list[dict]) -> list[dict]:
        """Analyse a batch of sensor readings and flag anomalies.

        Args:
            readings: List of dicts, each with at least ``sensor_id``,
                      ``temperature``, and ``vibration`` keys.

        Returns:
            List of result dicts, one per input reading, each augmented with:
              - ``is_anomaly`` (bool)
              - ``anomaly_scores`` mapping metric names to their z-scores
              - ``anomalous_metrics`` listing which metrics exceeded threshold
        """
        if not readings:
            return []

        temperatures = np.array([r["temperature"] for r in readings], dtype=float)
        vibrations = np.array([r["vibration"] for r in readings], dtype=float)

        temp_scores = self._modified_z_scores(temperatures)
        vib_scores = self._modified_z_scores(vibrations)

        results = []
        for i, reading in enumerate(readings):
            anomalous_metrics = []
            if temp_scores[i] > self.threshold:
                anomalous_metrics.append("temperature")
            if vib_scores[i] > self.threshold:
                anomalous_metrics.append("vibration")

            results.append({
                "sensor_id": reading["sensor_id"],
                "temperature": reading["temperature"],
                "vibration": reading["vibration"],
                "is_anomaly": len(anomalous_metrics) > 0,
                "anomaly_scores": {
                    "temperature": round(float(temp_scores[i]), 4),
                    "vibration": round(float(vib_scores[i]), 4),
                },
                "anomalous_metrics": anomalous_metrics,
            })

        return results
