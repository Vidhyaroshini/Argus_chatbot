import os
from datetime import datetime, timedelta, timezone
import httpx
from dotenv import load_dotenv

load_dotenv()
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")

# This metric name comes from the included demo service. Change it to match your own instrumentation.
P95_QUERY = 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="demo-api"}[5m])) by (le))'
ERROR_RATE_QUERY = '100 * sum(rate(http_requests_total{job="demo-api",status=~"5.."}[5m])) / clamp_min(sum(rate(http_requests_total{job="demo-api"}[5m])), 1e-9)'
REQUEST_RATE_QUERY = 'sum(rate(http_requests_total{job="demo-api"}[5m]))'


async def _get(path: str, params: dict):
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{PROMETHEUS_URL}{path}", params=params)
        response.raise_for_status()
        payload = response.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    return payload["data"]["result"]


async def instant_query(query: str):
    return await _get("/api/v1/query", {"query": query})


async def range_query(query: str, hours: int = 24, step_seconds: int = 300):
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    result = await _get("/api/v1/query_range", {
        "query": query,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "step": f"{step_seconds}s",
    })
    return result


def scalar_from_vector(result):
    if not result:
        return None
    try:
        return float(result[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


async def current_metrics():
    p95, errors, rate = await __import__("asyncio").gather(
        instant_query(P95_QUERY),
        instant_query(ERROR_RATE_QUERY),
        instant_query(REQUEST_RATE_QUERY),
    )
    p95_seconds = scalar_from_vector(p95)
    error_rate = scalar_from_vector(errors)
    request_rate = scalar_from_vector(rate)
    return {
        "p95_latency_ms": round(p95_seconds * 1000, 2) if p95_seconds is not None else None,
        "error_rate_percent": round(error_rate, 2) if error_rate is not None else None,
        "requests_per_second": round(request_rate, 3) if request_rate is not None else None,
        "note": "Values are derived from Prometheus; null means there are not yet enough samples or the metric is unavailable.",
    }


async def latency_history(hours: int = 24):
    result = await range_query(P95_QUERY, hours=hours, step_seconds=300 if hours <= 24 else 1800)
    points = []
    for series in result:
        for timestamp, value in series.get("values", []):
            try:
                points.append({"timestamp": datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat(),
                               "latency_ms": round(float(value) * 1000, 2)})
            except (TypeError, ValueError):
                continue
    return sorted(points, key=lambda p: p["timestamp"])
