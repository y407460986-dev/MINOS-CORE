"""SQLAlchemy async models and database initialization for minos_platform."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncGenerator

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, relationship

if TYPE_CHECKING:
    from pathlib import Path

Base = declarative_base()

# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------


class Project(Base):
    __tablename__ = "ppap_projects"

    id = Column(String(64), primary_key=True)
    name = Column(String(256), nullable=False)
    project_code = Column(String(128), nullable=True)
    part_number = Column(String(128), nullable=True)
    status = Column(String(64), nullable=False, default="created")
    created_at = Column(DateTime, nullable=False, default=lambda: _utc_now())


class InputPackage(Base):
    __tablename__ = "ppap_input_packages"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("ppap_projects.id"), nullable=False)
    package_path = Column(String(512), nullable=False)
    sha256 = Column(String(64), nullable=False)
    redacted = Column(String(16), nullable=False, default="unknown")
    created_at = Column(DateTime, nullable=False, default=lambda: _utc_now())

    project = relationship("Project", back_populates="input_packages")


class Run(Base):
    __tablename__ = "ppap_runs"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("ppap_projects.id"), nullable=False)
    run_type = Column(String(32), nullable=False)
    status = Column(String(64), nullable=False, default="created")
    result_json_path = Column(String(512), nullable=True)
    manifest_json_path = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: _utc_now())

    project = relationship("Project", back_populates="runs")
    artifacts = relationship("Artifact", back_populates="run", cascade="all, delete-orphan")
    review_patches = relationship(
        "ReviewPatch", back_populates="run", cascade="all, delete-orphan"
    )


class Artifact(Base):
    __tablename__ = "ppap_artifacts"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("ppap_runs.id"), nullable=True)
    artifact_type = Column(String(64), nullable=False)
    file_path = Column(String(512), nullable=False)
    sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: _utc_now())

    run = relationship("Run", back_populates="artifacts")


class ReviewPatch(Base):
    __tablename__ = "ppap_review_patches"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("ppap_runs.id"), nullable=True)
    project_id = Column(String(64), ForeignKey("ppap_projects.id"), nullable=False)
    patch_path = Column(String(512), nullable=False)
    sha256 = Column(String(64), nullable=False)
    submitted_at = Column(DateTime, nullable=False, default=lambda: _utc_now())

    run = relationship("Run", back_populates="review_patches")
    project = relationship("Project", back_populates="review_patches")


# ---------------------------------------------------------------------------
# Relationship back-links (added after class definitions to satisfy linters)
# ---------------------------------------------------------------------------

Project.input_packages = relationship("InputPackage", back_populates="project")
Project.runs = relationship("Run", back_populates="project")
Project.review_patches = relationship("ReviewPatch", back_populates="project")


# ---------------------------------------------------------------------------
# Engine / session helpers
# ---------------------------------------------------------------------------

_engine = None
_session_factory = None


async def init_db(db_url: str) -> None:
    """Create all tables if they don't exist. Idempotent — skips if already initialized."""
    global _engine, _session_factory
    if _engine is not None and _session_factory is not None:
        return  # Already initialized, skip
    _engine = create_async_engine(db_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes — yields an AsyncSession."""
    if _session_factory is None:
        raise RuntimeError("init_db() must be called before get_session()")
    async with _session_factory() as session:
        yield session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
