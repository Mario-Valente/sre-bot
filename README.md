# SRE Copilot

Bot autônomo para triage inicial de incidentes críticos. Analisa alertas do Alertmanager, coleta dados de Prometheus/Loki/Tempo/GitHub e gera análise de causa raiz usando LLM.

## Requisitos

- Python 3.11+
- Docker
- Kind, kubectl, Helm (para ambiente local K8s)

## Setup Rápido

### 1. Ambiente Kubernetes Local

```bash
# Criar cluster Kind + instalar Prometheus, Loki, Tempo, Grafana
./k8s/scripts/setup-cluster.sh
```

Acesse:
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090
- Loki: http://localhost:3100
- Tempo: http://localhost:3200

### 2. Configuração

```bash
cp .env.example .env
```

Edite `.env` com suas credenciais:

```bash
# LLM (escolha um)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_SIGNING_SECRET=...

# GitHub (opcional)
GITHUB_TOKEN=ghp-...
GITHUB_ORG=sua-org

# Logs
LOG_LEVEL=INFO
```

### 3. Instalar e Rodar

```bash
# Instalar
pip install -e .

# Rodar
sre-copilot
```

## Uso

### Via Webhook (Alertmanager)

Configure o Alertmanager para enviar webhooks:

```yaml
receivers:
  - name: 'sre-copilot'
    webhook_configs:
      - url: 'http://localhost:8000/webhook/alertmanager'
```

### Via Slack

- Poste um alerta no canal configurado → Bot analisa automaticamente
- Mencione o bot: `@sre-copilot analyze payment-api`
- Slash command: `/sre-analyze payment-api production`

### Via API

```bash
curl -X POST http://localhost:8000/webhook/custom \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "payment-api",
    "severity": "critical",
    "namespace": "production"
  }'
```

## Testes

```bash
pip install -e ".[dev]"
pytest
```

## Cleanup

```bash
./k8s/scripts/teardown-cluster.sh
```
