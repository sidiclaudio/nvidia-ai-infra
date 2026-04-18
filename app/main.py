import time
import random
import logging
from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# Three metrics that mirror what you would monitor on a real Triton server:
#   - REQUEST_COUNT   → tracks total requests by endpoint and status code
#   - REQUEST_LATENCY → histogram of response times (used for p99 SLO)
#   - INFERENCE_ERRORS → counts failed inference calls specifically
# These feed directly into the Grafana dashboard you will build on Evening 4.
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "inference_requests_total",
    "Total number of inference requests",
    ["endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "inference_request_duration_seconds",
    "Inference request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)

INFERENCE_ERRORS = Counter(
    "inference_errors_total",
    "Total number of inference errors",
    ["error_type"]
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/health", methods=["GET"])
def health():
    """
    Liveness probe endpoint.
    Kubernetes calls this to decide if the pod should be restarted.
    Returns 200 as long as the app process is running.
    Interview talking point: "I separate liveness from readiness —
    liveness checks if the app is alive, readiness checks if it can
    serve traffic. This prevents Kubernetes from sending requests to
    a pod that is still warming up."
    """
    return jsonify({"status": "healthy"}), 200


@app.route("/ready", methods=["GET"])
def ready():
    """
    Readiness probe endpoint.
    Kubernetes calls this before routing traffic to the pod.
    In a real Triton server this would check if the model is loaded.
    Returns 503 if the app is not ready to serve.
    """
    return jsonify({"status": "ready"}), 200


@app.route("/v2/models/mock-model/infer", methods=["POST"])
def infer():
    """
    Mock inference endpoint that mirrors Triton's HTTP inference API path.
    Accepts a JSON payload with an 'inputs' key and returns a mock prediction.

    Interview talking point: "I modelled the endpoint path after the real
    Triton HTTP API (/v2/models/{model_name}/infer) so the CI/CD pipeline
    and Helm chart configs are realistic. Swapping this mock for the real
    Triton container only requires changing the image tag."
    """
    start = time.time()

    try:
        payload = request.get_json(force=True)

        # Validate input — a real inference server would validate tensor shapes
        if not payload or "inputs" not in payload:
            REQUEST_COUNT.labels(endpoint="/infer", status="400").inc()
            INFERENCE_ERRORS.labels(error_type="invalid_input").inc()
            return jsonify({"error": "Missing 'inputs' key in request body"}), 400

        # Simulate variable inference latency (5ms – 150ms)
        # This gives the Grafana latency histogram something realistic to show
        simulated_latency = random.uniform(0.005, 0.150)
        time.sleep(simulated_latency)

        # Simulate a 2% error rate — realistic for a production inference server
        # This lets you demonstrate SLO alerting when error budget is consumed
        if random.random() < 0.02:
            raise RuntimeError("Simulated model inference failure")

        response = {
            "model_name": "mock-model",
            "model_version": "1",
            "outputs": [
                {
                    "name": "prediction",
                    "datatype": "FP32",
                    "shape": [1, 10],
                    "data": [round(random.random(), 4) for _ in range(10)]
                }
            ]
        }

        duration = time.time() - start
        REQUEST_COUNT.labels(endpoint="/infer", status="200").inc()
        REQUEST_LATENCY.labels(endpoint="/infer").observe(duration)
        logger.info(f"Inference OK latency={duration:.3f}s")
        return jsonify(response), 200

    except RuntimeError as e:
        duration = time.time() - start
        REQUEST_COUNT.labels(endpoint="/infer", status="500").inc()
        INFERENCE_ERRORS.labels(error_type="model_failure").inc()
        REQUEST_LATENCY.labels(endpoint="/infer").observe(duration)
        logger.error(f"Inference error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/metrics", methods=["GET"])
def metrics():
    """
    Prometheus scrape endpoint.
    Returns all metrics in the Prometheus text exposition format.
    Prometheus scrapes this every 15 seconds (configured in prometheus.yaml).

    Interview talking point: "I expose metrics from the app itself rather
    than relying only on infrastructure-level metrics. This gives me
    request-level SLIs — latency p99, error rate, throughput — which
    is what an SLO is actually measured against."
    """
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
