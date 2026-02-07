"""Unit tests for the AnomalyDetector class."""

import json

import numpy as np
import pytest

from src.detector import AnomalyDetector
from src.lambda_function import lambda_handler


# ---------------------------------------------------------------------------
# Detector unit tests
# ---------------------------------------------------------------------------

class TestAnomalyDetector:
    """Tests for the Modified Z-Score anomaly detection engine."""

    @pytest.fixture()
    def detector(self):
        return AnomalyDetector(threshold=3.5)

    @pytest.fixture()
    def normal_readings(self):
        """20 readings with values clustered in a normal range."""
        np.random.seed(42)
        return [
            {
                "sensor_id": f"sensor-{i:02d}",
                "temperature": float(np.random.normal(70, 2)),
                "vibration": float(np.random.normal(0.5, 0.05)),
            }
            for i in range(20)
        ]

    def test_no_anomalies_in_normal_data(self, detector, normal_readings):
        results = detector.detect(normal_readings)
        assert all(not r["is_anomaly"] for r in results)

    def test_detects_temperature_spike(self, detector, normal_readings):
        normal_readings.append({
            "sensor_id": "sensor-spike",
            "temperature": 200.0,
            "vibration": 0.5,
        })
        results = detector.detect(normal_readings)
        spike_result = next(r for r in results if r["sensor_id"] == "sensor-spike")
        assert spike_result["is_anomaly"] is True
        assert "temperature" in spike_result["anomalous_metrics"]

    def test_detects_vibration_spike(self, detector, normal_readings):
        normal_readings.append({
            "sensor_id": "sensor-vib",
            "temperature": 70.0,
            "vibration": 5.0,
        })
        results = detector.detect(normal_readings)
        spike_result = next(r for r in results if r["sensor_id"] == "sensor-vib")
        assert spike_result["is_anomaly"] is True
        assert "vibration" in spike_result["anomalous_metrics"]

    def test_detects_multi_metric_anomaly(self, detector, normal_readings):
        normal_readings.append({
            "sensor_id": "sensor-both",
            "temperature": 300.0,
            "vibration": 10.0,
        })
        results = detector.detect(normal_readings)
        spike_result = next(r for r in results if r["sensor_id"] == "sensor-both")
        assert spike_result["is_anomaly"] is True
        assert "temperature" in spike_result["anomalous_metrics"]
        assert "vibration" in spike_result["anomalous_metrics"]

    def test_empty_readings_returns_empty(self, detector):
        assert detector.detect([]) == []

    def test_identical_values_no_false_positives(self, detector):
        readings = [
            {"sensor_id": f"s-{i}", "temperature": 70.0, "vibration": 0.5}
            for i in range(10)
        ]
        results = detector.detect(readings)
        assert all(not r["is_anomaly"] for r in results)

    def test_custom_threshold(self):
        # A lower threshold should flag more readings as anomalous
        strict = AnomalyDetector(threshold=1.0)
        np.random.seed(99)
        readings = [
            {
                "sensor_id": f"s-{i}",
                "temperature": float(np.random.normal(70, 5)),
                "vibration": float(np.random.normal(0.5, 0.1)),
            }
            for i in range(30)
        ]
        results = strict.detect(readings)
        assert any(r["is_anomaly"] for r in results)

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            AnomalyDetector(threshold=-1)

    def test_result_schema(self, detector, normal_readings):
        results = detector.detect(normal_readings)
        for r in results:
            assert "sensor_id" in r
            assert "is_anomaly" in r
            assert "anomaly_scores" in r
            assert "temperature" in r["anomaly_scores"]
            assert "vibration" in r["anomaly_scores"]
            assert "anomalous_metrics" in r


# ---------------------------------------------------------------------------
# Lambda handler integration tests
# ---------------------------------------------------------------------------

class TestLambdaHandler:
    """Tests for the Lambda entry-point."""

    def _make_event(self, body: dict | str) -> dict:
        if isinstance(body, dict):
            body = json.dumps(body)
        return {"body": body}

    def test_successful_request(self):
        event = self._make_event({
            "readings": [
                {"sensor_id": "p-01", "temperature": 70, "vibration": 0.5},
                {"sensor_id": "p-02", "temperature": 71, "vibration": 0.48},
            ]
        })
        response = lambda_handler(event, None)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["total_readings"] == 2

    def test_missing_readings_key(self):
        event = self._make_event({"data": []})
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_missing_sensor_fields(self):
        event = self._make_event({
            "readings": [{"sensor_id": "p-01"}]
        })
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        assert "missing keys" in json.loads(response["body"])["error"]

    def test_malformed_json(self):
        event = {"body": "{not valid json}"}
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_anomaly_flagged_in_response(self):
        readings = [
            {"sensor_id": f"s-{i}", "temperature": 70.0, "vibration": 0.5}
            for i in range(20)
        ]
        readings.append({"sensor_id": "s-outlier", "temperature": 500.0, "vibration": 0.5})
        event = self._make_event({"readings": readings})
        response = lambda_handler(event, None)
        body = json.loads(response["body"])
        assert body["anomalies_detected"] >= 1
