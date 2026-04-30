#!/usr/bin/env bash
# =============================================================================
# SRE Copilot - Local Kubernetes Development Environment Setup
# =============================================================================
# This script sets up a complete local Kubernetes environment using Kind
# with Prometheus, Loki, Tempo, and Grafana using official Helm charts.
#
# Prerequisites:
#   - kind (https://kind.sigs.k8s.io/)
#   - kubectl
#   - helm
#
# Usage:
#   ./k8s/scripts/setup-cluster.sh
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CLUSTER_NAME="sre-bot"
NAMESPACE="monitoring"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
K8S_DIR="${PROJECT_ROOT}/k8s"

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    local missing=()

    if ! command -v kind &> /dev/null; then
        missing+=("kind")
    fi

    if ! command -v kubectl &> /dev/null; then
        missing+=("kubectl")
    fi

    if ! command -v helm &> /dev/null; then
        missing+=("helm")
    fi

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing required tools: ${missing[*]}"
        echo ""
        echo "Install them using:"
        echo "  brew install kind kubectl helm"
        echo ""
        exit 1
    fi

    log_success "All prerequisites met"
}

# -----------------------------------------------------------------------------
# Cluster management
# -----------------------------------------------------------------------------

create_cluster() {
    log_info "Creating Kind cluster '${CLUSTER_NAME}'..."

    # Check if cluster already exists
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log_warning "Cluster '${CLUSTER_NAME}' already exists"
        read -p "Delete and recreate? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kind delete cluster --name "${CLUSTER_NAME}"
        else
            log_info "Using existing cluster"
            return 0
        fi
    fi

    kind create cluster \
        --config "${K8S_DIR}/kind/cluster-config.yaml" \
        --name "${CLUSTER_NAME}"

    log_success "Cluster created"
}

setup_helm_repos() {
    log_info "Setting up Helm repositories..."

    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
    helm repo add grafana https://grafana.github.io/helm-charts || true
    helm repo update

    log_success "Helm repositories configured"
}

create_namespace() {
    log_info "Creating namespace '${NAMESPACE}'..."

    kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    log_success "Namespace ready"
}

# -----------------------------------------------------------------------------
# Install observability stack
# -----------------------------------------------------------------------------

install_prometheus_stack() {
    log_info "Installing kube-prometheus-stack..."

    helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        --namespace "${NAMESPACE}" \
        --values "${K8S_DIR}/helm-values/kube-prometheus-stack.yaml" \
        --wait \
        --timeout 10m

    log_success "Prometheus stack installed"
}

install_loki() {
    log_info "Installing Loki..."

    helm upgrade --install loki grafana/loki \
        --namespace "${NAMESPACE}" \
        --values "${K8S_DIR}/helm-values/loki.yaml" \
        --wait \
        --timeout 10m

    log_success "Loki installed"
}

install_tempo() {
    log_info "Installing Tempo..."

    helm upgrade --install tempo grafana/tempo \
        --namespace "${NAMESPACE}" \
        --values "${K8S_DIR}/helm-values/tempo.yaml" \
        --wait \
        --timeout 10m

    log_success "Tempo installed"
}

# -----------------------------------------------------------------------------
# Verification
# -----------------------------------------------------------------------------

wait_for_pods() {
    log_info "Waiting for all pods to be ready..."

    kubectl wait --for=condition=Ready pods \
        --all \
        --namespace "${NAMESPACE}" \
        --timeout=300s || {
        log_warning "Some pods may not be ready yet"
        kubectl get pods -n "${NAMESPACE}"
    }

    log_success "Pods are ready"
}

print_access_info() {
    echo ""
    echo "============================================================================="
    echo -e "${GREEN}SRE Copilot Development Environment Ready!${NC}"
    echo "============================================================================="
    echo ""
    echo "Access URLs (via NodePort):"
    echo "  - Grafana:    http://localhost:3000  (admin/admin)"
    echo "  - Prometheus: http://localhost:9090"
    echo "  - Loki:       http://localhost:3100"
    echo "  - Tempo:      http://localhost:3200"
    echo ""
    echo "Useful commands:"
    echo "  kubectl get pods -n ${NAMESPACE}     # Check pods"
    echo "  kubectl logs -f <pod> -n ${NAMESPACE} # View logs"
    echo "  kind delete cluster --name ${CLUSTER_NAME}  # Delete cluster"
    echo ""
    echo "Run SRE Copilot locally:"
    echo "  cp .env.example .env"
    echo "  # Edit .env with your API keys"
    echo "  pip install -e ."
    echo "  sre-copilot"
    echo ""
    echo "============================================================================="
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    echo ""
    echo "============================================================================="
    echo "SRE Copilot - Local Kubernetes Development Environment Setup"
    echo "============================================================================="
    echo ""

    check_prerequisites
    create_cluster
    setup_helm_repos
    create_namespace
    install_prometheus_stack
    install_loki
    install_tempo
    wait_for_pods
    print_access_info
}

# Run main function
main "$@"
