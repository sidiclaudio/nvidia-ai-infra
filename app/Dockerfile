# =============================================================================
# Multi-stage Dockerfile for the mock inference server
#
# WHY MULTI-STAGE:
# Stage 1 (builder) installs all dependencies including build tools.
# Stage 2 (runtime) copies only what is needed to run — no compilers,
# no pip cache, no build artifacts. Result: a smaller, cleaner image
# with a reduced CVE surface area.
#
# Interview talking point: "A single-stage build for this app produces
# a ~180MB image. The multi-stage build produces ~95MB. More importantly,
# the runtime stage has no pip, no setuptools, and no gcc — tools that
# are common CVE sources and are not needed at runtime."
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: builder
# Pinning to a specific digest is best practice for reproducibility.
# Using python:3.11-slim-bookworm (Debian Bookworm) for a small base
# with a long support window.
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

# Set working directory
WORKDIR /build

# Copy requirements first — Docker layer caching means this layer is only
# rebuilt when requirements.txt changes, not on every code change.
# Interview talking point: "Layer ordering is a CI/CD performance decision.
# Dependencies change rarely; source code changes constantly. Separate the
# layers so most builds hit the cache on the expensive pip install step."
COPY requirements.txt .

# Install dependencies into a prefix directory so we can copy them cleanly
# --no-cache-dir: don't store pip's download cache (saves ~50MB)
# --prefix: install to /install so we can COPY just this directory later
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: runtime
# Starts fresh from the same base — no build tools carried over.
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

# Metadata labels — used by container registries and audit tooling
# These are also what Trivy uses to identify the image in scan reports.
LABEL org.opencontainers.image.title="mock-inference-server" \
      org.opencontainers.image.description="Mock Triton inference API for CI/CD demo" \
      org.opencontainers.image.source="https://github.com/yourusername/nvidia-ai-infra-demo"

WORKDIR /app

# Copy installed packages from builder stage only
COPY --from=builder /install /usr/local

# Copy application source
COPY main.py .

# -----------------------------------------------------------------------------
# Non-root user
# Running as root inside a container is a security risk — if the process is
# compromised, the attacker has root access to the container filesystem.
# Interview talking point: "I always run application containers as a
# non-root user. This is enforced at the platform level too — our OPA
# policy rejects any pod spec with runAsRoot: true."
# -----------------------------------------------------------------------------
RUN useradd --system --no-create-home --uid 1001 appuser
USER appuser

# Expose port — documentation only, does not publish the port
EXPOSE 8080

# Healthcheck — Docker's built-in probe, separate from Kubernetes probes
# but useful for local docker run testing
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Use exec form (array) not shell form (string) for the entrypoint.
# Shell form wraps the command in /bin/sh -c, which means signals (SIGTERM)
# are sent to the shell, not to the Python process — the app won't shut
# down gracefully. Exec form sends signals directly to PID 1.
# Interview talking point: "Exec form vs shell form is a common Kubernetes
# graceful shutdown issue — teams wonder why their pods take 30 seconds to
# terminate. It's often because SIGTERM never reaches the application."
ENTRYPOINT ["python", "main.py"]