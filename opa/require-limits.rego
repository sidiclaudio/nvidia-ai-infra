# =============================================================================
# OPA Policy: require-limits.rego
#
# WHAT THIS DOES:
# Rejects any Kubernetes Pod or Deployment manifest that is missing CPU or
# memory resource limits on any container.
#
# WHY THIS MATTERS:
# A container without resource limits can consume unlimited CPU and memory,
# starving other workloads on the same node. This is the most common cause
# of "noisy neighbor" incidents in shared Kubernetes clusters.
#
# For GPU workloads this is even more critical — a container that does not
# declare nvidia.com/gpu resource limits will not be scheduled on a GPU node
# by the NVIDIA device plugin, but it also won't prevent other containers
# from competing for node resources.
#
# Interview talking point: "I enforce this at two layers: OPA Conftest in
# CI catches it before code is merged. OPA Gatekeeper on the cluster catches
# anything that bypasses CI — manual kubectl apply, for example. Defense in
# depth means a policy violation is caught at the earliest possible point."
# =============================================================================

package main

import future.keywords.if
import future.keywords.in

# ---------------------------------------------------------------------------
# Rule: deny pods missing resource limits
#
# This rule fires for any Pod manifest where any container is missing
# either cpu or memory limits. The deny set accumulates all violations
# so the developer sees every problem at once, not just the first one.
# ---------------------------------------------------------------------------
deny[msg] if {
    input.kind == "Pod"
    container := input.spec.containers[_]
    missing_limits(container)
    msg := sprintf(
        "Container '%s' in Pod '%s' must define resource limits for cpu and memory. Found: %v",
        [container.name, input.metadata.name, container.resources]
    )
}

deny[msg] if {
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    missing_limits(container)
    msg := sprintf(
        "Container '%s' in Deployment '%s' must define resource limits for cpu and memory.",
        [container.name, input.metadata.name]
    )
}

# ---------------------------------------------------------------------------
# Rule: deny containers running as root
#
# Interview talking point: "Running as root inside a container is a
# security risk. If the process is compromised, the attacker has root
# access to the container filesystem and potentially the host if the
# container runtime has a vulnerability. I enforce non-root at the
# policy level so it can't be accidentally omitted."
# ---------------------------------------------------------------------------
deny[msg] if {
    input.kind == "Pod"
    container := input.spec.containers[_]
    container.securityContext.runAsUser == 0
    msg := sprintf(
        "Container '%s' must not run as root (runAsUser: 0). Set runAsUser to a non-zero UID.",
        [container.name]
    )
}

deny[msg] if {
    input.kind == "Pod"
    not input.spec.securityContext.runAsNonRoot
    not input.spec.securityContext.runAsUser
    msg := sprintf(
        "Pod '%s' must set securityContext.runAsNonRoot: true or an explicit non-zero runAsUser.",
        [input.metadata.name]
    )
}

# ---------------------------------------------------------------------------
# Rule: require readiness and liveness probes
#
# Interview talking point: "Without a readiness probe, Kubernetes sends
# traffic to a pod the moment it starts — before the app is ready to serve.
# Without a liveness probe, a deadlocked process sits there forever
# receiving traffic and returning errors. Both probes are non-negotiable
# for production workloads."
# ---------------------------------------------------------------------------
deny[msg] if {
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    not container.readinessProbe
    msg := sprintf(
        "Container '%s' in Deployment '%s' must define a readinessProbe.",
        [container.name, input.metadata.name]
    )
}

deny[msg] if {
    input.kind == "Deployment"
    container := input.spec.template.spec.containers[_]
    not container.livenessProbe
    msg := sprintf(
        "Container '%s' in Deployment '%s' must define a livenessProbe.",
        [container.name, input.metadata.name]
    )
}

# ---------------------------------------------------------------------------
# Helper function: checks if a container is missing cpu or memory limits
# ---------------------------------------------------------------------------
missing_limits(container) if {
    not container.resources.limits.cpu
}

missing_limits(container) if {
    not container.resources.limits.memory
}


# =============================================================================
# TEST CASES
# Run with: opa test opa/
# OPA inline tests run automatically — the policy itself is tested,
# not just the manifests it validates.
# =============================================================================

# Test: a fully compliant pod should produce zero denials
test_compliant_pod_passes if {
    count(deny) == 0 with input as {
        "kind": "Pod",
        "metadata": {"name": "good-pod"},
        "spec": {
            "securityContext": {"runAsNonRoot": true, "runAsUser": 1001},
            "containers": [{
                "name": "app",
                "image": "myapp:latest",
                "resources": {
                    "limits":   {"cpu": "500m", "memory": "256Mi"},
                    "requests": {"cpu": "100m", "memory": "128Mi"}
                },
                "readinessProbe": {"httpGet": {"path": "/ready",  "port": 8080}},
                "livenessProbe":  {"httpGet": {"path": "/health", "port": 8080}}
            }]
        }
    }
}

# Test: missing cpu limit must be denied
test_missing_cpu_limit_denied if {
    count(deny) > 0 with input as {
        "kind": "Pod",
        "metadata": {"name": "bad-pod"},
        "spec": {
            "securityContext": {"runAsNonRoot": true},
            "containers": [{
                "name": "app",
                "resources": {"limits": {"memory": "256Mi"}}
            }]
        }
    }
}

# Test: missing memory limit must be denied
test_missing_memory_limit_denied if {
    count(deny) > 0 with input as {
        "kind": "Pod",
        "metadata": {"name": "bad-pod"},
        "spec": {
            "securityContext": {"runAsNonRoot": true},
            "containers": [{
                "name": "app",
                "resources": {"limits": {"cpu": "500m"}}
            }]
        }
    }
}

# Test: container running as root must be denied
test_root_container_denied if {
    count(deny) > 0 with input as {
        "kind": "Pod",
        "metadata": {"name": "root-pod"},
        "spec": {
            "containers": [{
                "name": "app",
                "securityContext": {"runAsUser": 0},
                "resources": {
                    "limits": {"cpu": "500m", "memory": "256Mi"}
                }
            }]
        }
    }
}