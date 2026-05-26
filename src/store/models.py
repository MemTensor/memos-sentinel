"""Database models — AuditLog, PendingAction, TaskQueue, LLMUsage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)
    event_action = Column(String(50))
    target_number = Column(Integer)
    result_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(String(36), primary_key=True)
    action_type = Column(String(50), nullable=False)
    target = Column(String(100), nullable=False)
    details = Column(Text)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class TaskQueue(Base):
    __tablename__ = "task_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_number = Column(Integer, nullable=False)
    task_type = Column(String(50), nullable=False)
    status = Column(String(20), default="queued")
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model = Column(String(100), nullable=False)
    purpose = Column(String(50), nullable=False)  # classify | ai_task_judge | review | dev_analyze | dev_fix | reflection
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    target_number = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
