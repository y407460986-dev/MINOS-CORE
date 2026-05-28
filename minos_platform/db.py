"""SQLAlchemy async models and database initialization for minos_platform."""

from __future__ import annotations

import asyncio
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


class SchemaVersion(Base):
    __tablename__ = "ppap_schema_version"

    id = Column(String(64), primary_key=True, default="platform_v1")
    version = Column(String(64), nullable=False)
    initialized_at = Column(DateTime, nullable=False, default=lambda: _utc_now())


class PPAPPackage(Base):
    __tablename__ = "ppap_packages"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("ppap_projects.id"), nullable=False)
    name = Column(String(256), nullable=False)
    submission_level = Column(String(32), nullable=True)
    status = Column(String(32), nullable=False, default="draft")
    created_at = Column(DateTime, nullable=False, default=lambda: _utc_now())

    project = relationship("Project", back_populates="ppap_packages")
    elements = relationship("PPAPElement", back_populates="package", cascade="all, delete-orphan")


class PPAPElement(Base):
    __tablename__ = "ppap_package_elements"

    id = Column(String(64), primary_key=True)
    package_id = Column(String(64), ForeignKey("ppap_packages.id"), nullable=False)
    element_key = Column(String(64), nullable=False)
    display_name = Column(String(256), nullable=False)
    status = Column(String(32), nullable=False, default="missing")
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: _utc_now())

    package = relationship("PPAPPackage", back_populates="elements")
    artifacts = relationship("PPAPElementArtifact", back_populates="element", cascade="all, delete-orphan")


class PPAPElementArtifact(Base):
    __tablename__ = "ppap_element_artifacts"

    id = Column(String(64), primary_key=True)
    element_id = Column(String(64), ForeignKey("ppap_package_elements.id"), nullable=False)
    artifact_id = Column(String(64), ForeignKey("ppap_artifacts.id"), nullable=True)
    artifact_ref_path = Column(String(512), nullable=True)
    sha256 = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: _utc_now())

    element = relationship("PPAPElement", back_populates="artifacts")
    artifact = relationship("Artifact")


# ---------------------------------------------------------------------------
# Relationship back-links (added after class definitions to satisfy linters)
# ---------------------------------------------------------------------------

Project.input_packages = relationship("InputPackage", back_populates="project")
Project.runs = relationship("Run", back_populates="project")
Project.review_patches = relationship("ReviewPatch", back_populates="project")
Project.ppap_packages = relationship("PPAPPackage", back_populates="project")


# ---------------------------------------------------------------------------
# Engine / session helpers
# ---------------------------------------------------------------------------

_engine = None
_session_factory = None
_init_lock = asyncio.Lock()  # SECURITY FIX v3.1.0: Prevent race conditions


PLATFORM_SCHEMA_VERSION = "platform_v1"


async def init_db(db_url: str) -> None:
    """Create all tables if they don't exist. Thread-safe initialization.

    SECURITY FIX v3.1.0: Uses asyncio.Lock to prevent race conditions.
    """
    global _engine, _session_factory

    async with _init_lock:
        # Double-check pattern inside lock
        if _engine is not None and _session_factory is not None:
            return  # Already initialized by another task

        _engine = create_async_engine(db_url, echo=False)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Upsert schema version record
            await conn.run_sync(_upsert_schema_version)


def _upsert_schema_version(connection) -> None:
    """Insert or replace the platform schema version marker."""
    from sqlalchemy import text
    connection.execute(text(
        "INSERT OR REPLACE INTO ppap_schema_version (id, version, initialized_at) "
        "VALUES (:id, :version, :now)"
    ), {"id": PLATFORM_SCHEMA_VERSION, "version": PLATFORM_SCHEMA_VERSION, "now": _utc_now()})


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes — yields an AsyncSession."""
    if _session_factory is None:
        raise RuntimeError("init_db() must be called before get_session()")
    async with _session_factory() as session:
        yield session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
