from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Float, Boolean, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin

class Workflow(Base, TimestampMixin):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    
    executions: Mapped[List["WorkflowExecution"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")
    states: Mapped[List["WorkflowStateModel"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")
    epics: Mapped[List["Epic"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")
    requirements: Mapped[List["Requirement"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")
    stories: Mapped[List["UserStory"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")

class WorkflowExecution(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workflow_executions"
    
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    workflow: Mapped["Workflow"] = relationship(back_populates="executions")
    logs: Mapped[List["LLMExecutionLog"]] = relationship(back_populates="execution", cascade="all, delete-orphan")

class WorkflowStateModel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workflow_states"
    
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_node: Mapped[str] = mapped_column(String(100))
    state_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    workflow: Mapped["Workflow"] = relationship(back_populates="states")

class Requirement(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "requirements"
    
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    req_type: Mapped[str] = mapped_column(String(50), default="FUNCTIONAL") # FUNCTIONAL, NON_FUNCTIONAL
    
    workflow: Mapped["Workflow"] = relationship(back_populates="requirements")

class Epic(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "epics"
    
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    workflow: Mapped["Workflow"] = relationship(back_populates="epics")
    features: Mapped[List["Feature"]] = relationship(back_populates="epic", cascade="all, delete-orphan")

class Feature(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "features"
    
    epic_id: Mapped[str] = mapped_column(ForeignKey("epics.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    epic: Mapped["Epic"] = relationship(back_populates="features")

class UserStory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_stories"
    
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    feature_id: Mapped[Optional[str]] = mapped_column(ForeignKey("features.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(Text)
    business_value: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list) # Store as JSON list
    status: Mapped[str] = mapped_column(String(50), default="GENERATED")
    
    workflow: Mapped["Workflow"] = relationship(back_populates="stories")
    feature: Mapped[Optional["Feature"]] = relationship()
    validation_results: Mapped[List["ValidationResult"]] = relationship(back_populates="story", cascade="all, delete-orphan")
    reviews: Mapped[List["Review"]] = relationship(back_populates="story", cascade="all, delete-orphan")

class ValidationResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "validation_results"
    
    story_id: Mapped[str] = mapped_column(ForeignKey("user_stories.id", ondelete="CASCADE"), index=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    issues: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)
    
    story: Mapped["UserStory"] = relationship(back_populates="validation_results")

class Review(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reviews"
    
    story_id: Mapped[str] = mapped_column(ForeignKey("user_stories.id", ondelete="CASCADE"), index=True)
    reviewer: Mapped[str] = mapped_column(String(255))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    story: Mapped["UserStory"] = relationship(back_populates="reviews")

class AuditLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_logs"
    
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(100))
    changes: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

class LLMExecutionLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "llm_execution_logs"
    
    execution_id: Mapped[Optional[str]] = mapped_column(ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    execution: Mapped[Optional["WorkflowExecution"]] = relationship(back_populates="logs")
