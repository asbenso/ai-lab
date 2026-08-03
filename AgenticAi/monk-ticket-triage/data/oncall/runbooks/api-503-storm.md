<!-- source: https://internal.example.com/runbooks/oncall/api-503-storm -->

# API gateway 503 storm

## Symptoms

- Sudden spike in HTTP 503 responses from api-gateway.
- Circuit breaker opens for an upstream service.
- P95 latency exceeds SLO for core routes.

## Common causes

1. Upstream database connection pool exhaustion.
2. Bad deploy increasing query latency.
3. Traffic surge without autoscaling.

## Resolution steps

1. Confirm blast radius in the gateway dashboard and error budget burn.
2. Check upstream health (`api-core` db pool, postgres latency).
3. If tied to a recent deploy, roll back to the last known good version.
4. Scale api-core replicas if pool saturation is due to load, not a leak.

## Escalation

Page the platform on-call lead if rollback does not restore error rate below 5% within 15 minutes.
