# nvidia-ai-infra

A mock NVIDIA Triton inference server built with Flask and instrumented with Prometheus metrics. Designed as a realistic stand-in for a Triton HTTP endpoint — useful for building and testing ML infrastructure (CI/CD pipelines, Helm charts, Grafana dashboards) without needing a real GPU or model.

## What it does

- Exposes a Triton-compatible inference endpoint at `POST /v2/models/mock-model/infer`
- Simulates realistic inference latency (5–150ms) and a 2% error rate
- Emits Prometheus metrics for request count, latency histogram, and error count
- Exposes Kubernetes liveness and readiness probes

## Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness probe — returns `200` while the process is alive |
| `/ready` | GET | Readiness probe — returns `200` when ready to serve traffic |
| `/v2/models/mock-model/infer` | POST | Mock inference — accepts a JSON payload with an `inputs` key |
| `/metrics` | GET | Prometheus scrape endpoint |

### Inference request format

```json
{
  "inputs": [
    {
      "name": "input",
      "shape": [1, 3],
      "datatype": "FP32",
      "data": [1.0, 2.0, 3.0]
    }
  ]
}
```

### Inference response format

```json
{
  "model_name": "mock-model",
  "model_version": "1",
  "outputs": [
    {
      "name": "prediction",
      "datatype": "FP32",
      "shape": [1, 10],
      "data": [0.2676, 0.4433, 0.4405, ...]
    }
  ]
}
```

## Running locally

**Install dependencies:**
```bash
pip install -r app/requirements.txt
```

**Start the server:**
```bash
python app/main.py
```

The server listens on `http://localhost:8080`.

**Smoke test:**
```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/v2/models/mock-model/infer \
  -H "Content-Type: application/json" \
  -d '{"inputs": [{"name": "input", "shape": [1,3], "datatype": "FP32", "data": [1.0, 2.0, 3.0]}]}'
```

## Running with Docker

**Build:**
```bash
docker build -t mock-inference-server ./app
```

**Run:**
```bash
docker run -p 8080:8080 mock-inference-server
```

The image uses a multi-stage build (builder + runtime) to keep the final image lean (~95MB vs ~180MB single-stage) and free of build tools that add CVE surface area.

## Running tests

```bash
cd app
pytest test_main.py -v
```

Tests use Flask's test client (no live server needed) and mock `time.sleep` and `random.random` to make the test suite fast and deterministic. Covered cases: happy path, invalid input (400), empty body (400), simulated model failure (500), and Prometheus metrics format.

## Metrics

Three custom Prometheus metrics are exposed at `/metrics`:

| Metric | Type | Labels |
|---|---|---|
| `inference_requests_total` | Counter | `endpoint`, `status` |
| `inference_request_duration_seconds` | Histogram | `endpoint` |
| `inference_errors_total` | Counter | `error_type` |

## Project structure

```
nvidia-ai-infra/
└── app/
    ├── main.py           # Flask app
    ├── test_main.py      # pytest test suite
    ├── Dockerfile        # Multi-stage Docker build
    └── requirements.txt  # Pinned dependencies
```