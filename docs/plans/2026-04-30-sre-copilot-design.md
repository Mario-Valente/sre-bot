# SRE Copilot Agent - Design Document

**Data:** 2026-04-30
**Status:** Aprovado
**Stack:** Python, LangChain, LangGraph, slack_bolt

---

## 1. Visão Geral

Bot do Slack autônomo que faz triage inicial de incidentes críticos. Recebe alertas do Alertmanager, coleta dados de múltiplas fontes (Prometheus, Loki, Tempo, GitHub), e gera uma análise de causa raiz (RCA) inicial usando LLM.

### 1.1 Decisões Arquiteturais

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| LLM Provider | Dinâmico (OpenAI/Claude via env) | Flexibilidade para trocar providers |
| Input Sources | Webhook + Slack Listener (feature flags) | Configurável por ambiente |
| Persistência | SQLite (dev) / PostgreSQL (prod) | Histórico de incidentes + analytics |
| Clients HTTP | Interface abstrata (Protocol) | Testabilidade + trocar backends |
| GitHub | API direta (não MCP) | Menos complexidade no MVP |
| Queries | Templates pré-definidos | Segurança - LLM não gera PromQL/LogQL |

---

## 2. Estrutura de Diretórios

```
sre-bot/
├── src/
│   └── sre_copilot/
│       ├── __init__.py
│       ├── main.py                 # Entrypoint - inicia Slack + Webhook
│       ├── config.py               # Settings via pydantic-settings (env vars)
│       │
│       ├── agent/                  # Core do LangGraph
│       │   ├── __init__.py
│       │   ├── state.py            # Pydantic models do State
│       │   ├── graph.py            # Definição do grafo (nós + arestas)
│       │   └── nodes/              # Cada nó do grafo
│       │       ├── __init__.py
│       │       ├── extract_context.py
│       │       ├── fetch_metrics.py
│       │       ├── fetch_logs.py
│       │       ├── fetch_traces.py
│       │       ├── fetch_github.py
│       │       ├── synthesize.py
│       │       └── post_to_slack.py
│       │
│       ├── tools/                  # LangChain Tools (wrappers)
│       │   ├── __init__.py
│       │   ├── prometheus.py
│       │   ├── loki.py
│       │   ├── tempo.py
│       │   └── github.py
│       │
│       ├── clients/                # Clients HTTP (implementações)
│       │   ├── __init__.py
│       │   ├── protocols.py        # Abstract interfaces (Protocol)
│       │   ├── prometheus.py
│       │   ├── loki.py
│       │   ├── tempo.py
│       │   └── github.py
│       │
│       ├── queries/                # Templates de queries (segurança)
│       │   ├── __init__.py
│       │   ├── prometheus.py       # PromQL templates
│       │   ├── loki.py             # LogQL templates
│       │   └── tempo.py            # TraceQL templates
│       │
│       ├── integrations/           # Slack + Webhook handlers
│       │   ├── __init__.py
│       │   ├── slack.py            # slack_bolt app
│       │   └── webhook.py          # FastAPI receiver
│       │
│       ├── llm/                    # Factory para LLM dinâmico
│       │   ├── __init__.py
│       │   └── factory.py
│       │
│       └── db/                     # Persistência
│           ├── __init__.py
│           ├── models.py           # SQLAlchemy models
│           └── repository.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── docs/
│   └── plans/
│
├── pyproject.toml
├── .env.example
└── docker-compose.yml
```

---

## 3. LangGraph State

```python
from typing import Literal
from pydantic import BaseModel, Field
from datetime import datetime


class AlertContext(BaseModel):
    """Dados extraídos do alerta original."""
    alert_name: str
    severity: Literal["critical", "warning", "info"]
    service_name: str
    cluster: str
    namespace: str
    pod: str | None = None
    status_code: int | None = None
    timestamp: datetime
    raw_payload: dict


class MetricsData(BaseModel):
    """Resultado da consulta Prometheus."""
    cpu_usage: list[dict] | None = None
    memory_usage: list[dict] | None = None
    error_rate_5xx: list[dict] | None = None
    latency_p99: list[dict] | None = None
    anomalies_detected: list[str] = Field(default_factory=list)


class LogsData(BaseModel):
    """Resultado da consulta Loki."""
    error_logs: list[dict] = Field(default_factory=list)
    fatal_logs: list[dict] = Field(default_factory=list)
    log_patterns: list[str] = Field(default_factory=list)


class TracesData(BaseModel):
    """Resultado da consulta Tempo."""
    failed_traces: list[dict] = Field(default_factory=list)
    slow_traces: list[dict] = Field(default_factory=list)
    bottleneck_services: list[str] = Field(default_factory=list)


class GitHubData(BaseModel):
    """Mudanças recentes no repositório."""
    recent_commits: list[dict] = Field(default_factory=list)
    recent_prs: list[dict] = Field(default_factory=list)
    last_release: dict | None = None
    has_recent_deploy: bool = False


class IncidentAnalysis(BaseModel):
    """Análise final sintetizada pelo LLM."""
    summary: str
    probable_root_cause: str
    contributing_factors: list[str]
    evidence: list[str]
    suggested_actions: list[str]
    confidence: Literal["high", "medium", "low"]
    needs_human_escalation: bool


class AgentState(BaseModel):
    """State principal que flui pelo grafo."""
    # Input
    alert: AlertContext

    # Dados coletados
    metrics: MetricsData | None = None
    logs: LogsData | None = None
    traces: TracesData | None = None
    github: GitHubData | None = None

    # Output
    analysis: IncidentAnalysis | None = None

    # Metadata
    slack_thread_ts: str | None = None
    slack_channel: str | None = None
    errors: list[str] = Field(default_factory=list)
```

---

## 4. Fluxo do Grafo

```
                    ┌─────────────────┐
                    │  START (Alert)  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ extract_context │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │fetch_metrics│   │ fetch_logs  │   │fetch_traces │  ← Paralelo
   │ (Prometheus)│   │   (Loki)    │   │   (Tempo)   │
   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  fetch_github   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   synthesize    │  ← LLM
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  post_to_slack  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │       END       │
                    └─────────────────┘
```

### 4.1 Código do Grafo

```python
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from sre_copilot.agent.state import AgentState
from sre_copilot.agent.nodes import (
    extract_context,
    fetch_metrics,
    fetch_logs,
    fetch_traces,
    fetch_github,
    synthesize,
    post_to_slack,
)


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    # Nós
    graph.add_node("extract_context", extract_context)
    graph.add_node("fetch_metrics", fetch_metrics)
    graph.add_node("fetch_logs", fetch_logs)
    graph.add_node("fetch_traces", fetch_traces)
    graph.add_node("fetch_github", fetch_github)
    graph.add_node("synthesize", synthesize)
    graph.add_node("post_to_slack", post_to_slack)

    # Arestas
    graph.add_edge(START, "extract_context")

    # Fan-out paralelo
    graph.add_edge("extract_context", "fetch_metrics")
    graph.add_edge("extract_context", "fetch_logs")
    graph.add_edge("extract_context", "fetch_traces")

    # Fan-in
    graph.add_edge("fetch_metrics", "fetch_github")
    graph.add_edge("fetch_logs", "fetch_github")
    graph.add_edge("fetch_traces", "fetch_github")

    # Sequência final
    graph.add_edge("fetch_github", "synthesize")
    graph.add_edge("synthesize", "post_to_slack")
    graph.add_edge("post_to_slack", END)

    return graph.compile()
```

---

## 5. Query Templates (Segurança)

A LLM **nunca** gera queries. Templates pré-definidos por SREs com sanitização de inputs.

```python
from enum import Enum
from string import Template


class MetricType(str, Enum):
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    ERROR_RATE = "error_rate"
    LATENCY_P99 = "latency_p99"
    REQUEST_RATE = "request_rate"


PROMETHEUS_TEMPLATES: dict[MetricType, Template] = {
    MetricType.CPU_USAGE: Template(
        'rate(container_cpu_usage_seconds_total{namespace="$namespace", pod=~"$service.*"}[5m])'
    ),
    MetricType.MEMORY_USAGE: Template(
        'container_memory_usage_bytes{namespace="$namespace", pod=~"$service.*"}'
    ),
    MetricType.ERROR_RATE: Template(
        'sum(rate(http_requests_total{namespace="$namespace", service="$service", status=~"5.."}[5m])) '
        '/ sum(rate(http_requests_total{namespace="$namespace", service="$service"}[5m]))'
    ),
    MetricType.LATENCY_P99: Template(
        'histogram_quantile(0.99, '
        'sum(rate(http_request_duration_seconds_bucket{namespace="$namespace", service="$service"}[5m])) '
        'by (le))'
    ),
}


def build_query(metric_type: MetricType, service: str, namespace: str) -> str:
    _validate_label(service, "service")
    _validate_label(namespace, "namespace")

    template = PROMETHEUS_TEMPLATES[metric_type]
    return template.safe_substitute(service=service, namespace=namespace)


def _validate_label(value: str, name: str) -> None:
    forbidden = set('"{}\n\\')
    if any(c in forbidden for c in value):
        raise ValueError(f"Invalid characters in {name}: {value}")
    if len(value) > 128:
        raise ValueError(f"{name} too long: {len(value)} chars")
```

---

## 6. Interfaces Abstratas (Protocols)

```python
from typing import Protocol, Any
from datetime import datetime


class MetricsClient(Protocol):
    async def query(self, query: str) -> list[dict[str, Any]]: ...
    async def query_range(
        self, query: str, start: datetime, end: datetime, step: str = "15s"
    ) -> list[dict[str, Any]]: ...


class LogsClient(Protocol):
    async def query(
        self, query: str, start: datetime, end: datetime, limit: int = 1000
    ) -> list[dict[str, Any]]: ...


class TracesClient(Protocol):
    async def search(
        self, service_name: str, start: datetime, end: datetime,
        min_duration: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]: ...
    async def get_trace(self, trace_id: str) -> dict[str, Any]: ...


class GitClient(Protocol):
    async def get_recent_commits(
        self, repo: str, since: datetime, limit: int = 10
    ) -> list[dict[str, Any]]: ...
    async def get_recent_prs(
        self, repo: str, state: str = "merged", since: datetime | None = None, limit: int = 10
    ) -> list[dict[str, Any]]: ...
    async def get_latest_release(self, repo: str) -> dict[str, Any] | None: ...
```

---

## 7. Configuração

```python
from enum import Enum
from pydantic_settings import BaseSettings
from pydantic import SecretStr


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class Settings(BaseSettings):
    # LLM
    llm_provider: LLMProvider = LLMProvider.OPENAI
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    llm_temperature: float = 0.1

    # Input Sources (Feature Flags)
    enable_webhook: bool = True
    enable_slack_listener: bool = True
    webhook_port: int = 8000

    # Slack
    slack_bot_token: SecretStr
    slack_app_token: SecretStr
    slack_signing_secret: SecretStr

    # Observability
    prometheus_url: str = "http://localhost:9090"
    loki_url: str = "http://localhost:3100"
    tempo_url: str = "http://localhost:3200"

    # GitHub
    github_token: SecretStr | None = None
    github_org: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./sre_bot.db"

    # Timeouts
    query_timeout_seconds: float = 30.0
    llm_timeout_seconds: float = 60.0
```

---

## 8. LLM Factory

```python
from functools import lru_cache
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    match settings.llm_provider:
        case LLMProvider.OPENAI:
            return ChatOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                model=settings.openai_model,
                temperature=settings.llm_temperature,
            )
        case LLMProvider.ANTHROPIC:
            return ChatAnthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                model=settings.anthropic_model,
                temperature=settings.llm_temperature,
            )
```

---

## 9. Próximos Passos (Implementação)

1. Setup do projeto (pyproject.toml, estrutura de pastas)
2. Implementar `config.py` e `llm/factory.py`
3. Implementar `agent/state.py`
4. Implementar `clients/protocols.py` e `clients/prometheus.py`
5. Implementar `queries/prometheus.py`
6. Implementar nós do grafo (`agent/nodes/`)
7. Implementar `agent/graph.py`
8. Implementar integrações Slack e Webhook
9. Testes unitários e de integração
10. Docker Compose para ambiente local
