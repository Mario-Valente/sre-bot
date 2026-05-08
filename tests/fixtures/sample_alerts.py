"""Sample alert payloads for testing."""

from datetime import datetime

# Sample Alertmanager webhook payload
ALERTMANAGER_WEBHOOK_FIRING = {
    "version": "4",
    "groupKey": '{}:{alertname="HighErrorRate"}',
    "truncatedAlerts": 0,
    "status": "firing",
    "receiver": "sre-copilot",
    "groupLabels": {
        "alertname": "HighErrorRate",
    },
    "commonLabels": {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "service": "payment-api",
        "namespace": "production",
        "cluster": "main",
    },
    "commonAnnotations": {
        "summary": "High error rate detected in payment-api",
        "description": "Error rate is above 5% for the last 5 minutes",
        "runbook_url": "https://runbooks.example.com/high-error-rate",
    },
    "externalURL": "http://alertmanager:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighErrorRate",
                "severity": "critical",
                "service": "payment-api",
                "namespace": "production",
                "cluster": "main",
                "pod": "payment-api-5d4f6b7c8-abc12",
            },
            "annotations": {
                "summary": "High error rate detected in payment-api",
                "description": "Error rate is above 5% for the last 5 minutes",
                "runbook_url": "https://runbooks.example.com/high-error-rate",
            },
            "startsAt": "2024-01-15T10:30:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://prometheus:9090/graph?...",
            "fingerprint": "abc123def456",
        }
    ],
}

ALERTMANAGER_WEBHOOK_RESOLVED = {
    "version": "4",
    "groupKey": '{}:{alertname="HighErrorRate"}',
    "truncatedAlerts": 0,
    "status": "resolved",
    "receiver": "sre-copilot",
    "groupLabels": {
        "alertname": "HighErrorRate",
    },
    "commonLabels": {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "service": "payment-api",
        "namespace": "production",
        "cluster": "main",
    },
    "commonAnnotations": {
        "summary": "High error rate detected in payment-api",
        "description": "Error rate is above 5% for the last 5 minutes",
    },
    "externalURL": "http://alertmanager:9093",
    "alerts": [
        {
            "status": "resolved",
            "labels": {
                "alertname": "HighErrorRate",
                "severity": "critical",
                "service": "payment-api",
                "namespace": "production",
                "cluster": "main",
            },
            "annotations": {
                "summary": "High error rate detected in payment-api",
                "description": "Error rate is above 5% for the last 5 minutes",
            },
            "startsAt": "2024-01-15T10:30:00Z",
            "endsAt": "2024-01-15T10:45:00Z",
            "generatorURL": "http://prometheus:9090/graph?...",
            "fingerprint": "abc123def456",
        }
    ],
}

# Sample Prometheus query response
PROMETHEUS_QUERY_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {
                    "__name__": "http_requests_total",
                    "service": "payment-api",
                    "status": "500",
                },
                "values": [
                    [1705315800, "10"],
                    [1705315815, "15"],
                    [1705315830, "25"],
                    [1705315845, "18"],
                    [1705315860, "12"],
                ],
            }
        ],
    },
}

# Sample Loki query response
LOKI_QUERY_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "streams",
        "result": [
            {
                "stream": {
                    "app": "payment-api",
                    "namespace": "production",
                    "level": "error",
                },
                "values": [
                    [
                        "1705315830000000000",
                        '{"level":"error","msg":"Connection refused to database","timestamp":"2024-01-15T10:30:30Z"}',
                    ],
                    [
                        "1705315835000000000",
                        '{"level":"error","msg":"Timeout waiting for database connection","timestamp":"2024-01-15T10:30:35Z"}',
                    ],
                ],
            }
        ],
    },
}

# Sample Tempo search response
TEMPO_SEARCH_RESPONSE = {
    "traces": [
        {
            "traceID": "abc123def456",
            "rootServiceName": "payment-api",
            "rootTraceName": "POST /api/payments",
            "startTimeUnixNano": "1705315830000000000",
            "durationMs": 1500,
            "spanSets": [],
        },
        {
            "traceID": "ghi789jkl012",
            "rootServiceName": "payment-api",
            "rootTraceName": "GET /api/payments/{id}",
            "startTimeUnixNano": "1705315835000000000",
            "durationMs": 2500,
            "spanSets": [],
        },
    ]
}

# Sample GitHub commits response
GITHUB_COMMITS_RESPONSE = [
    {
        "sha": "abc123def456ghi789",
        "commit": {
            "author": {
                "name": "John Doe",
                "date": "2024-01-15T10:00:00Z",
            },
            "message": "Fix database connection handling\n\nIncreased connection pool size",
        },
        "html_url": "https://github.com/org/payment-api/commit/abc123",
    },
    {
        "sha": "def456ghi789jkl012",
        "commit": {
            "author": {
                "name": "Jane Smith",
                "date": "2024-01-15T09:30:00Z",
            },
            "message": "Update dependencies",
        },
        "html_url": "https://github.com/org/payment-api/commit/def456",
    },
]
