#!/usr/bin/env bash
# =============================================================================
# SRE Copilot - Delete Local Kubernetes Development Environment
# =============================================================================
# This script removes the Kind cluster and all associated resources.
#
# Usage:
#   ./k8s/scripts/teardown-cluster.sh
# =============================================================================

set -euo pipefail

CLUSTER_NAME="sre-bot"

echo "Deleting Kind cluster '${CLUSTER_NAME}'..."

if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    kind delete cluster --name "${CLUSTER_NAME}"
    echo "Cluster deleted successfully"
else
    echo "Cluster '${CLUSTER_NAME}' does not exist"
fi
