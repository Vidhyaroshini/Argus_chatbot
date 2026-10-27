import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Legend } from "recharts";
import "./style.css";

const API = "http://127.0.0.1:8000";

function ChartPanel({ chart }) {
  if (!chart || !Array.isArray(chart.data) || chart.data.length === 0) {
    if (chart) return <p className="muted">No chart samples yet. Generate traffic against the demo API and wait for Prometheus to scrape it.</p>;
    return null;
  }
  if (chart.type === "line") {
    const data = chart.data.map((p) => ({ ...p, time: p.timestamp ? new Date(p.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "" }));
    return <section className="chart"><h3>{chart.title}</h3><ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="time" minTickGap={30} /><YAxis unit={` ${chart.unit || ""}`} /><Tooltip /><Line type="monotone" dataKey={chart.yKey || "latency_ms"} dot={false} strokeWidth={2} /></LineChart>
    </ResponsiveContainer></section>;
  }
  if (chart.type === "pie") {
    const palette = ["#3867d6", "#eb3b5a", "#20bf6b", "#f7b731", "#8854d0"];
    return <section className="chart"><h3>{chart.title}</h3><ResponsiveContainer width="100%" height={280}>
      <PieChart><Pie data={chart.data} dataKey={chart.valueKey || "count"} nameKey={chart.nameKey || "severity"} outerRadius={90} label>{chart.data.map((entry, i) => <Cell key={i} fill={palette[i % palette.length]} />)}</Pie><Tooltip /><Legend /></PieChart>
    </ResponsiveContainer></section>;
  }
  return null;
}

function App() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([{ role: "assistant", text: "Hi! Ask about current latency, past incidents, or request a graph." }]);
  const [loading, setLoading] = useState(false);

  async function sendQuestion(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || loading) return;
    setMessages((old) => [...old, { role: "user", text: q }]);
    setQuestion("");
    setLoading(true);
    try {
      const response = await fetch(`${API}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Request failed");
      setMessages((old) => [...old, { role: "assistant", text: result.answer || JSON.stringify(result), result }]);
    } catch (err) {
      setMessages((old) => [...old, { role: "assistant", text: `Could not reach backend: ${err.message}. Check that FastAPI is running on port 8000.` }]);
    } finally { setLoading(false); }
  }

  return <main className="page">
    <header><div><p className="eyebrow">OBSERVABILITY ASSISTANT</p><h1>Incident Investigation Chatbot</h1><p className="muted">Live metrics · Incident history · Evidence-based triage</p></div><span className="pill">Prototype</span></header>
    <section className="suggestions">
      {["What is the current latency?", "Why is API latency high?", "Show latency for the last 24 hours", "Show a pie chart of incidents by severity", "Show previous incidents"].map((s) => <button key={s} onClick={() => setQuestion(s)}>{s}</button>)}
    </section>
    <section className="chat">
      {messages.map((m, i) => <article key={i} className={`message ${m.role}`}><div className="role">{m.role === "user" ? "You" : "Assistant"}</div><p>{m.text}</p>
        {m.result?.metrics && <div className="metric-cards">{Object.entries(m.result.metrics).filter(([k, v]) => k !== "note" && v !== null).map(([k, v]) => <div className="metric" key={k}><small>{k.replaceAll("_", " ")}</small><strong>{v}{k.includes("percent") ? "%" : k.includes("latency") ? " ms" : ""}</strong></div>)}</div>}
        <ChartPanel chart={m.result?.chart} />
        {m.result?.incidents && <div className="incidents">{m.result.incidents.map((inc) => <div className="incident" key={inc.id}><b>{inc.title}</b><span className={`severity ${inc.severity}`}>{inc.severity}</span><p>{inc.description}</p><small>Resolution: {inc.resolution}</small></div>)}</div>}
      </article>)}
      {loading && <div className="message assistant"><p>Checking monitoring data and incident history…</p></div>}
    </section>
    <form className="composer" onSubmit={sendQuestion}><input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about an incident, latency, or history…" /><button disabled={loading || !question.trim()}>{loading ? "Working…" : "Send"}</button></form>
    <footer>Metrics are queried from Prometheus; historical incidents come from PostgreSQL. Root-cause statements are hypotheses unless supported by sufficient evidence.</footer>
  </main>;
}

createRoot(document.getElementById("root")).render(<App />);
