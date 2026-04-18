"""
Unit tests for the mock inference server.

Interview talking point: "I test three things: happy path, error handling,
and the contract of the API — input validation. I keep unit tests fast
(no network, no sleep) by mocking the random latency. Integration tests
that hit a real running server are a separate test suite run in CI after
the Docker image is built."
"""
import json
import pytest
from unittest.mock import patch
from main import app


# ---------------------------------------------------------------------------
# Test client fixture
# Flask provides a test client so tests run without a real HTTP server.
# This keeps the test suite fast — each test runs in milliseconds.
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# Health and readiness probe tests
# These matter for Kubernetes: if these endpoints return non-200,
# the kubelet will restart or stop routing traffic to the pod.
# ---------------------------------------------------------------------------
class TestProbes:

    def test_health_returns_200(self, client):
        """Liveness probe must always return 200 while the process is running."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "healthy"

    def test_ready_returns_200(self, client):
        """Readiness probe returns 200 when app is ready to serve traffic."""
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ready"


# ---------------------------------------------------------------------------
# Inference endpoint tests
# ---------------------------------------------------------------------------
class TestInference:

    @patch("main.time.sleep")          # skip simulated latency in tests
    @patch("main.random.random", return_value=0.5)   # deterministic: no error
    def test_valid_request_returns_200(self, mock_random, mock_sleep, client):
        """
        Happy path: a well-formed request returns a prediction payload
        that matches the Triton inference response schema.
        """
        payload = {"inputs": [{"name": "input", "shape": [1, 3], "datatype": "FP32"}]}
        response = client.post(
            "/v2/models/mock-model/infer",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["model_name"] == "mock-model"
        assert "outputs" in body
        assert len(body["outputs"][0]["data"]) == 10

    def test_missing_inputs_key_returns_400(self, client):
        """
        Input validation: requests without the 'inputs' key must be
        rejected with a 400. This prevents silent bad data from reaching
        the model — a real inference server validates tensor shapes here.
        """
        response = client.post(
            "/v2/models/mock-model/infer",
            data=json.dumps({"wrong_key": "data"}),
            content_type="application/json"
        )
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_empty_body_returns_400(self, client):
        """Empty request body should be rejected, not cause a 500 crash."""
        response = client.post(
            "/v2/models/mock-model/infer",
            data="",
            content_type="application/json"
        )
        assert response.status_code == 400

    @patch("main.time.sleep")
    @patch("main.random.random", return_value=0.0)   # force error path (< 0.02)
    def test_model_failure_returns_500(self, mock_random, mock_sleep, client):
        """
        Error simulation: when the random threshold triggers a model failure,
        the API must return 500 with an error message — not crash silently.
        Interview talking point: 'I test the error path explicitly because
        uninstrumented failures are how alert fatigue starts — silent 500s
        that never show up in metrics.'
        """
        payload = {"inputs": [{"name": "input", "shape": [1, 3], "datatype": "FP32"}]}
        response = client.post(
            "/v2/models/mock-model/infer",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert response.status_code == 500
        assert "error" in response.get_json()


# ---------------------------------------------------------------------------
# Metrics endpoint test
# ---------------------------------------------------------------------------
class TestMetrics:

    def test_metrics_endpoint_returns_prometheus_format(self, client):
        """
        The /metrics endpoint must return Prometheus text format.
        Prometheus will reject the scrape if Content-Type is wrong.
        """
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.content_type
        # Verify our custom metric names appear in the output
        data = response.data.decode("utf-8")
        assert "inference_requests_total" in data
        assert "inference_request_duration_seconds" in data