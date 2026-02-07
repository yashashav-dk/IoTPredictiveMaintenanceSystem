"""AWS Lambda entry-point for the IoT Predictive Maintenance API.

Accepts a JSON payload of sensor readings via API Gateway, runs anomaly
detection, and returns scored results.

Example event (API Gateway proxy integration)::

    {
        "body": "{\"readings\": [{\"sensor_id\": \"pump-01\", \"temperature\": 72.5, \"vibration\": 0.8}, ...]}"
    }
"""

import json
import logging
from typing import Any

from src.detector import AnomalyDetector

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Instantiated at module level so the object is reused across warm invocations.
detector = AnomalyDetector()


def _build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event: dict, context: Any) -> dict:
    """Process incoming sensor readings and return anomaly analysis.

    Args:
        event: API Gateway proxy event with a JSON ``body`` containing a
               ``readings`` list.
        context: Lambda context object (unused but required by the runtime).

    Returns:
        API Gateway-compatible response dict.
    """
    try:
        body = event.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)

        readings = body.get("readings")
        if not readings or not isinstance(readings, list):
            return _build_response(400, {
                "error": "Request must include a non-empty 'readings' list"
            })

        required_keys = {"sensor_id", "temperature", "vibration"}
        for idx, r in enumerate(readings):
            missing = required_keys - r.keys()
            if missing:
                return _build_response(400, {
                    "error": f"Reading at index {idx} is missing keys: {sorted(missing)}"
                })

        results = detector.detect(readings)

        anomaly_count = sum(1 for r in results if r["is_anomaly"])
        logger.info("Processed %d readings — %d anomalies detected", len(results), anomaly_count)

        return _build_response(200, {
            "total_readings": len(results),
            "anomalies_detected": anomaly_count,
            "results": results,
        })

    except json.JSONDecodeError:
        return _build_response(400, {"error": "Malformed JSON in request body"})
    except Exception:
        logger.exception("Unexpected error during processing")
        return _build_response(500, {"error": "Internal server error"})
