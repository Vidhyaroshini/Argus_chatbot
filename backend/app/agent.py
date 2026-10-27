import json
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from . import tools

load_dotenv()

SYSTEM_PROMPT = (
    "You are an incident investigation assistant. Use tools for live metrics and stored incidents. "
    "Never invent measurements. Separate observed evidence from hypotheses. A historical incident is not proof "
    "of the current root cause. If telemetry is missing, say so. If a chart is requested, return the chart object "
    "from the tool results. Be concise and practical."
)


async def answer_question(question: str, db: Session):
    # Optional OpenAI tool-calling mode. A deterministic fallback makes local setup possible without an API key.
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)
            tool_specs = [
                {"type": "function", "function": {"name": "get_current_metrics", "description": "Get current p95 latency, 5xx error rate, and request rate from Prometheus.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
                {"type": "function", "function": {"name": "get_latency_history", "description": "Get p95 latency history from Prometheus for 1, 6, 24, or 72 hours. Use when user asks for a graph or trend.", "parameters": {"type": "object", "properties": {"hours": {"type": "integer", "enum": [1, 6, 24, 72]}}, "required": ["hours"], "additionalProperties": False}}},
                {"type": "function", "function": {"name": "get_incident_history", "description": "Get recent historical incidents from PostgreSQL.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "additionalProperties": False}}},
                {"type": "function", "function": {"name": "get_incident_severity_counts", "description": "Count incidents by severity from PostgreSQL and return pie chart data.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
                {"type": "function", "function": {"name": "investigate_latency", "description": "Correlate current Prometheus latency/error metrics with historical PostgreSQL incidents and return evidence-based triage.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
            ]
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
            chart = None
            for _ in range(4):
                response = await client.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                    messages=messages, tools=tool_specs, tool_choice="auto", temperature=0.1,
                )
                msg = response.choices[0].message
                messages.append(msg)
                if not msg.tool_calls:
                    return {"answer": msg.content or "I could not produce an answer.", "chart": chart, "mode": "llm_tool_calling"}
                for call in msg.tool_calls:
                    args = json.loads(call.function.arguments or "{}")
                    name = call.function.name
                    if name == "get_current_metrics":
                        result = await tools.get_current_metrics()
                    elif name == "get_latency_history":
                        result = await tools.get_latency_history(args.get("hours", 24))
                        chart = result.get("chart")
                    elif name == "get_incident_history":
                        result = tools.get_incident_history(db, args.get("limit", 10))
                    elif name == "get_incident_severity_counts":
                        result = tools.get_incident_severity_counts(db)
                        chart = result.get("chart")
                    elif name == "investigate_latency":
                        result = await tools.investigate_latency(db)
                    else:
                        result = {"error": "Tool not allowed"}
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)})
            return {"answer": "The investigation reached its tool-call limit. Please try a narrower question.", "chart": chart, "mode": "llm_tool_calling"}
        except Exception as exc:
            # Avoid exposing secrets or stack traces to the user; fallback to deterministic routing.
            fallback = await deterministic_answer(question, db)
            fallback["note"] = "LLM call failed; used the local fallback router. Check backend logs/configuration."
            return fallback
    return await deterministic_answer(question, db)


async def deterministic_answer(question: str, db: Session):
    q = question.lower()
    if "current" in q and ("latency" in q or "metrics" in q or "metric" in q):
        metrics = await tools.get_current_metrics()
        return {"answer": "Current monitoring snapshot from Prometheus.", "metrics": metrics, "mode": "fallback"}
    if "pie" in q or ("severity" in q and ("chart" in q or "count" in q or "distribution" in q)):
        result = tools.get_incident_severity_counts(db)
        return {"answer": "Here is the historical incident distribution by severity from PostgreSQL.", "chart": result["chart"], "mode": "fallback"}
    if "previous" in q or "history" in q or "past incident" in q or "incidents" in q:
        incidents = tools.get_incident_history(db)
        return {"answer": "These are the most recent historical incident records stored in PostgreSQL.", "incidents": incidents, "mode": "fallback"}
    if "why" in q or "root cause" in q or "investigat" in q or "high" in q and "latency" in q:
        result = await tools.investigate_latency(db)
        lines = [result["conclusion"], "", "Evidence:"]
        lines += [f"- {item}" for item in result["evidence"]]
        if result["hypotheses"]:
            lines += ["", "Possible explanations (not confirmed):"] + [f"- {item}" for item in result["hypotheses"]]
        lines += ["", result["caveat"]]
        return {"answer": "\n".join(lines), "investigation": result, "mode": "fallback"}
    if "latency" in q or "graph" in q or "chart" in q or "last 24" in q or "trend" in q:
        result = await tools.get_latency_history(24)
        return {"answer": f"Retrieved {result['points_count']} p95 latency points from Prometheus.", "chart": result["chart"], "mode": "fallback"}
    metrics = await tools.get_current_metrics()
    return {"answer": "Current monitoring snapshot from Prometheus. Ask for latency history, previous incidents, or why latency is high for a deeper investigation.",
            "metrics": metrics, "mode": "fallback"}
