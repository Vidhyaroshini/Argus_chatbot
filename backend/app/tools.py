from sqlalchemy.orm import Session  # noqa: I001
from sqlalchemy import desc, func
from .db import Incident
from . import prometheus_client as prom


async def get_current_metrics():
    return await prom.current_metrics()


async def get_latency_history(hours: int = 24):
    if hours not in (1, 6, 24, 72):
        hours = 24
    points = await prom.latency_history(hours)
    return {
        "chart": {
            "type": "line",
            "title": f"API p95 latency — last {hours} hours",
            "xKey": "timestamp",
            "yKey": "latency_ms",
            "unit": "ms",
            "data": points,
        },
        "points_count": len(points),
    }


def get_incident_history(db: Session, limit: int = 10):
    rows = (
        db.query(Incident)
        .order_by(desc(Incident.created_at))
        .limit(min(max(limit, 1), 50))
        .all()
    )
    return [
        {
            "id": row.id,
            "title": row.title,
            "service": row.service,
            "severity": row.severity,
            "description": row.description,
            "suspected_cause": row.suspected_cause,
            "resolution": row.resolution,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def get_incident_severity_counts(db: Session):
    rows = (
        db.query(Incident.severity, func.count(Incident.id))
        .group_by(Incident.severity)
        .all()
    )
    data = [{"severity": severity, "count": count} for severity, count in rows]
    return {
        "chart": {
            "type": "pie",
            "title": "Historical incidents by severity",
            "nameKey": "severity",
            "valueKey": "count",
            "data": data,
        }
    }


async def investigate_latency(db: Session):
    metrics = await prom.current_metrics()
    history = get_incident_history(db, limit=10)
    p95 = metrics["p95_latency_ms"]
    errors = metrics["error_rate_percent"]
    evidence = []
    hypotheses = []

    if p95 is None:
        evidence.append(
            "Prometheus did not return a p95 latency value. There may be insufficient traffic, or the configured histogram metric/job may not exist."
        )
    else:
        evidence.append(f"Current p95 latency: {p95} ms.")
        if p95 > 500:
            hypotheses.append(
                "High request latency is confirmed by the current p95 metric (>500 ms)."
            )
        else:
            evidence.append("Current p95 is not above the starter threshold of 500 ms.")

    if errors is not None:
        evidence.append(f"Current 5xx error rate: {errors}%.")
        if errors > 2:
            hypotheses.append(
                "The 5xx error rate is elevated (>2%), which may accompany a failing dependency or application error."
            )
    else:
        evidence.append("Prometheus did not return an error-rate value.")

    similar = [
        item
        for item in history
        if any(
            word in (item["title"] + " " + item["description"]).lower()
            for word in ("slow", "latency", "pool", "dependency")
        )
    ]
    if similar:
        evidence.append(
            f"Found {len(similar)} potentially relevant historical incident(s) in PostgreSQL."
        )
        for item in similar[:3]:
            hypotheses.append(
                f"Historical reference only — {item['title']}: {item['suspected_cause']}"
            )
    else:
        evidence.append(
            "No obviously related historical incident was found in the recent incident records."
        )

    if p95 is not None and p95 > 500 and (errors is not None and errors > 2):
        conclusion = "Latency is high and the 5xx error rate is also elevated. Investigate application errors and downstream dependencies first; the available metrics alone do not prove a single root cause."
    elif p95 is not None and p95 > 500:
        conclusion = "The p95 latency metric indicates slow requests, but the current metric set does not establish why. Check traces, application logs, database latency, and recent deployments."
    elif p95 is None:
        conclusion = "I cannot assess current latency because the configured Prometheus query returned no usable p95 value. Verify the scrape target and histogram metric."
    else:
        conclusion = "The current p95 metric does not exceed the starter threshold. If users still report slowness, check per-route latency, traffic volume, traces, and logs."

    return {
        "conclusion": conclusion,
        "evidence": evidence,
        "hypotheses": hypotheses,
        "metrics": metrics,
        "historical_incidents": similar[:5],
        "caveat": "This is evidence-based triage, not a definitive root-cause determination. Logs, traces, database metrics, and deployment events improve confidence.",
    }
