from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import os
from .db import get_db, init_db_and_seed, ChatMessage
from .agent import answer_question
from . import tools

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_and_seed()
    yield


app = FastAPI(title="IArgus Chatbot API", version="0.1.0", lifespan=lifespan)
origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin, "https://chess-marry-handwork.ngrok-free.dev/v1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    try:
        result = await answer_question(payload.question, db)
        db.add(ChatMessage(question=payload.question, answer=result.get("answer", "")))
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="Investigation failed. Check Prometheus connectivity and backend logs.",
        ) from exc


@app.get("/api/metrics/current")
async def current_metrics():
    try:
        return await tools.get_current_metrics()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not query Prometheus. Check PROMETHEUS_URL and target health.",
        ) from exc


@app.get("/api/incidents")
def incidents(db: Session = Depends(get_db)):
    return {"incidents": tools.get_incident_history(db, 50)}


@app.get("/api/incidents/severity")
def incident_severity(db: Session = Depends(get_db)):
    return tools.get_incident_severity_counts(db)
