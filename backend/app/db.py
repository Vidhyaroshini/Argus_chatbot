import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://chatbot:chatbot_dev_password@localhost:5432/incident_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    service: Mapped[str] = mapped_column(String(100), nullable=False, default="employee-api")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suspected_cause: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db_and_seed():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(Incident).count() == 0:
            samples = [
                Incident(
                    title="Employee API slow after database pool saturation",
                    service="employee-api", severity="high",
                    description="p95 latency increased and database connection pool wait time rose.",
                    suspected_cause="Database connection pool saturation (historical finding; not proof of the current incident).",
                    resolution="Raised pool capacity after validating database limits and fixed a connection leak.",
                ),
                Incident(
                    title="Intermittent 5xx responses during deployment",
                    service="employee-api", severity="critical",
                    description="5xx responses increased shortly after a release.",
                    suspected_cause="A regression in the deployed version.",
                    resolution="Rolled back the release and added a regression test.",
                ),
                Incident(
                    title="Slow downstream employee-directory dependency",
                    service="employee-api", severity="medium",
                    description="Employee API latency followed an increase in dependency response time.",
                    suspected_cause="Downstream employee-directory service latency.",
                    resolution="Restored dependency health and added a timeout.",
                ),
            ]
            db.add_all(samples)
            db.commit()
