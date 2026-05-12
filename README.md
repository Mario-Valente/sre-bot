# SRE Copilot

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.28+-326CE5.svg?logo=kubernetes&logoColor=white)](https://kubernetes.io/)

AI-powered SRE assistant for autonomous incident triage and root cause analysis. Integrates with your observability stack (Prometheus, Loki, Tempo) and collaboration tools (Slack, GitHub) to accelerate incident response.

## Overview

SRE Copilot is an autonomous agent that:

- **Receives alerts** from Alertmanager webhooks or Slack channels
- **Collects context** from Prometheus metrics, Loki logs, Tempo traces, Kubernetes API, and GitHub
- **Analyzes root cause** using LLM (OpenAI GPT-4 or Anthropic Claude)
- **Reports findings** back to Slack with actionable insights

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────────────┐
│ Alertmanager│────▶│             │     │         Data Collection             │
└─────────────┘     │             │     │  ┌───────────┐  ┌───────────┐       │
                    │  SRE        │────▶│  │Prometheus │  │   Loki    │       │
┌─────────────┐     │  Copilot    │     │  └───────────┘  └───────────┘       │
│   Slack     │◀───▶│             │     │  ┌───────────┐  ┌───────────┐       │
└─────────────┘     │             │     │  │   Tempo   │  │ Kubernetes│       │
                    │             │     │  └───────────┘  └───────────┘       │
                    │             │     │  ┌───────────┐                      │
                    │             │     │  │  GitHub   │                      │
                    └─────────────┘     │  └───────────┘                      │
                           │            └─────────────────────────────────────┘
                           ▼
                    ┌─────────────┐
                    │  LLM (GPT-4 │
                    │  / Claude)  │
                    └─────────────┘
```

## Features

- **Multi-source Alert Ingestion**: Alertmanager webhooks, Slack messages, custom API
- **Comprehensive Data Collection**:
  - Prometheus: metrics, SLIs, error rates, latency percentiles
  - Loki: application logs with automatic error pattern detection
  - Tempo: distributed traces for failed requests
  - Kubernetes: pod status, events, logs, deployment info
  - GitHub: recent commits, deployments, PR context
- **Intelligent Analysis**: LLM-powered root cause synthesis with confidence scoring
- **Slack Integration**: Real-time alerts, interactive commands, threaded responses
- **Cloud Native**: Helm chart, HPA, health checks, structured logging

## Status

**Alpha** - Under active development. API may change.

## Prerequisites

| Component | Version | Required |
|-----------|---------|----------|
| Python | 3.11+ | Yes |
| Kubernetes | 1.28+ | For production |
| Helm | 3.x | For Helm install |
| Docker | 20.10+ | For container builds |

### Observability Stack

SRE Copilot expects these services to be available:

| Service | Purpose | Default URL |
|---------|---------|-------------|
| Prometheus | Metrics queries | `http://localhost:9090` |
| Loki | Log queries | `http://localhost:3100` |
| Tempo | Trace queries | `http://localhost:3200` |

## Installation

### Option 1: Helm (Recommended for Kubernetes)

```bash
# Add the Helm repository (if published)
helm repo add sre-copilot https://mario-valente.github.io/sre-bot

# Install with custom values
helm install sre-copilot sre-copilot/sre-copilot \
  --namespace sre-copilot \
  --create-namespace \
  -f values.yaml
```

Or install from source:

```bash
helm install sre-copilot ./k8s/charts/sre-bot \
  --namespace sre-copilot \
  --create-namespace \
  --set config.llmProvider=openai \
  --set secrets.openaiApiKey=$OPENAI_API_KEY \
  --set secrets.slackBotToken=$SLACK_BOT_TOKEN \
  --set secrets.slackAppToken=$SLACK_APP_TOKEN
```

### Option 2: Docker

```bash
docker build -t sre-copilot:latest .

docker run -d \
  --name sre-copilot \
  -p 8000:8000 \
  -e LLM_PROVIDER=openai \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN \
  -e SLACK_APP_TOKEN=$SLACK_APP_TOKEN \
  -e PROMETHEUS_URL=http://prometheus:9090 \
  sre-copilot:latest
```

### Option 3: Local Development

```bash
# Clone the repository
git clone https://github.com/Mario-Valente/sre-bot.git
cd sre-bot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run
sre-copilot
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

#### LLM Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | `openai` or `anthropic` | `openai` |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OPENAI_MODEL` | Model to use | `gpt-4o` |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `ANTHROPIC_MODEL` | Model to use | `claude-sonnet-4-20250514` |
| `LLM_TEMPERATURE` | Sampling temperature | `0.1` |

#### Slack Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_BOT_TOKEN` | Bot token (`xoxb-...`) | Yes |
| `SLACK_APP_TOKEN` | App token (`xapp-...`) | Yes |
| `SLACK_SIGNING_SECRET` | Webhook verification | Yes |
| `SLACK_ALERT_CHANNEL` | Channel to monitor | No |

#### Observability Stack

| Variable | Description | Default |
|----------|-------------|---------|
| `PROMETHEUS_URL` | Prometheus API endpoint | `http://localhost:9090` |
| `LOKI_URL` | Loki API endpoint | `http://localhost:3100` |
| `TEMPO_URL` | Tempo API endpoint | `http://localhost:3200` |

#### Kubernetes (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `KUBERNETES_ENABLED` | Enable K8s integration | `true` |
| `KUBERNETES_IN_CLUSTER` | Use in-cluster config | `false` |
| `KUBERNETES_CONTEXT` | kubeconfig context | Current context |

See [`.env.example`](.env.example) for all options.

## Usage

### Via Alertmanager Webhook

Configure Alertmanager to send alerts:

```yaml
# alertmanager.yml
receivers:
  - name: 'sre-copilot'
    webhook_configs:
      - url: 'http://sre-copilot:8000/webhook/alertmanager'
        send_resolved: false

route:
  receiver: 'sre-copilot'
  routes:
    - match:
        severity: critical
      receiver: 'sre-copilot'
```

### Via Slack

**Automatic Detection**: Post alerts in the configured channel - the bot analyzes automatically.

**Direct Mention**:
```
@sre-copilot analyze payment-api
```

**Slash Command**:
```
/sre-analyze payment-api production
```

### Via REST API

```bash
curl -X POST http://localhost:8000/webhook/custom \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "payment-api",
    "namespace": "production",
    "severity": "critical",
    "description": "High error rate detected"
  }'
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook/alertmanager` | POST | Alertmanager webhook receiver |
| `/webhook/custom` | POST | Custom alert ingestion |
| `/health` | GET | Health check |
| `/ready` | GET | Readiness check |

## Local Development Environment

Set up a complete local environment with Kind:

```bash
# Create Kind cluster with observability stack
./k8s/scripts/setup-cluster.sh
```

This installs:
- **Prometheus** (kube-prometheus-stack): http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Loki**: http://localhost:3100
- **Tempo**: http://localhost:3200

Teardown:
```bash
./k8s/scripts/teardown-cluster.sh
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests with coverage
pytest

# Run specific test file
pytest tests/test_agent.py -v

# Run with markers
pytest -m "not integration"
```

### Code Quality

```bash
# Linting
ruff check src/ tests/

# Formatting
ruff format src/ tests/

# Type checking
mypy src/

# All checks (via pre-commit)
pre-commit run --all-files
```

### Project Structure

```
sre-bot/
├── src/sre_copilot/
│   ├── agent/           # LangGraph agent definition
│   │   └── nodes/       # Agent workflow nodes
│   ├── clients/         # External service clients
│   │   ├── prometheus.py
│   │   ├── loki.py
│   │   ├── tempo.py
│   │   └── kubernetes.py
│   ├── integrations/    # Slack, webhook handlers
│   ├── llm/             # LLM provider abstraction
│   ├── queries/         # PromQL, LogQL query builders
│   └── db/              # Database models
├── k8s/
│   ├── charts/          # Helm chart
│   ├── scripts/         # Setup scripts
│   └── manifests/       # Raw K8s manifests
├── tests/
└── pyproject.toml
```

## Roadmap

- [ ] PagerDuty integration
- [ ] Datadog support
- [ ] Runbook automation
- [ ] Multi-cluster support
- [ ] Custom analysis plugins
- [ ] Incident timeline visualization

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/sre-bot.git

# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

## Community

- **Issues**: [GitHub Issues](https://github.com/Mario-Valente/sre-bot/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Mario-Valente/sre-bot/discussions)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with:
- [LangChain](https://langchain.com/) / [LangGraph](https://langchain-ai.github.io/langgraph/) - Agent framework
- [Slack Bolt](https://slack.dev/bolt-python/) - Slack integration
- [FastAPI](https://fastapi.tiangolo.com/) - Webhook receiver
- [kubernetes-client](https://github.com/kubernetes-client/python) - Kubernetes API
