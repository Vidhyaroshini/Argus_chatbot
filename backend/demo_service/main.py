import asyncio
from fastapi import FastAPI, Query
from prometheus_client import Counter, Histogram, make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

app = FastAPI(title="Demo API instrumented for Prometheus")

REQUESTS = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "status"])
DURATION = Histogram("http_request_duration_seconds", "HTTP request duration in seconds", ["method", "path"])


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        import time
        start = time.perf_counter()
        try:
            response = await call_next(request)
            return response
        except Exception:
            REQUESTS.labels(request.method, request.url.path, "500").inc()
            raise
        finally:
            elapsed = time.perf_counter() - start
            DURATION.labels(request.method, request.url.path).observe(elapsed)
            # Status is added in the normal response path below by a simpler explicit counter.
            # For middleware exception paths, the 500 counter is already incremented.


app.add_middleware(MetricsMiddleware)
app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health():
    REQUESTS.labels("GET", "/health", "200").inc()
    return {"status": "ok"}


@app.get("/work")
async def work(delay_ms: int = Query(default=100, ge=0, le=5000), fail: bool = False):
    await asyncio.sleep(delay_ms / 1000)
    if fail:
        REQUESTS.labels("GET", "/work", "500").inc()
        return Response(content='{"error":"simulated failure"}', media_type="application/json", status_code=500)
    REQUESTS.labels("GET", "/work", "200").inc()
    return {"status": "completed", "simulated_delay_ms": delay_ms}
