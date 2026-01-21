"""Workload data models.

Universal models for deployment state and configuration that
work across all workload types.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeploymentStatus(str, Enum):
    """Universal deployment status values."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    CLEANING_UP = "cleaning_up"


class DeploymentState(BaseModel):
    """Universal deployment state - same for all workloads.

    This is the common state object returned by all workloads
    for their deployments, enabling universal CLI commands.
    """

    deployment_id: str = Field(..., description="Unique deployment identifier")
    workload_name: str = Field(..., description="Name of the workload type")
    status: DeploymentStatus = Field(..., description="Current deployment status")
    phase: str = Field(default="unknown", description="Current execution phase")
    started_at: datetime | None = Field(default=None, description="When deployment started")
    stopped_at: datetime | None = Field(default=None, description="When deployment stopped")
    completed_at: datetime | None = Field(default=None, description="When deployment completed")
    config: dict[str, Any] = Field(default_factory=dict, description="Workload-specific config")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    error: str | None = Field(default=None, description="Error message if failed")

    class Config:
        use_enum_values = True


class DeploymentConfig(BaseModel):
    """Configuration for starting a new deployment.

    Base configuration that all workloads receive. Workloads
    can define additional fields in their own config models.
    """

    workload_name: str = Field(..., description="Name of workload to deploy")
    duration_hours: int | None = Field(default=None, description="Duration in hours (None = indefinite)")
    tags: dict[str, str] = Field(default_factory=dict, description="Tags for tracking")
    workload_config: dict[str, Any] = Field(default_factory=dict, description="Workload-specific config")


class WorkloadManifest(BaseModel):
    """Manifest describing a workload package.

    Read from workload.yaml in workload repositories.
    """

    name: str = Field(..., description="Workload name (unique identifier)")
    version: str = Field(..., description="Semantic version")
    description: str = Field(default="", description="Human-readable description")
    workload_type: str = Field(..., alias="type", description="'prompt' or 'runtime'")

    # Python package info (for runtime workloads)
    package: dict[str, str] | None = Field(default=None, description="Package install info")

    # Entry point for the workload class
    entrypoint: str | None = Field(default=None, description="Module:Class for workload")

    # Infrastructure extensions
    extensions: dict[str, Any] = Field(default_factory=dict, description="CLI/API extensions")

    # Target requirements
    targets: list[dict[str, Any]] = Field(default_factory=list, description="Target tenant requirements")

    class Config:
        populate_by_name = True


class CleanupReport(BaseModel):
    """Report returned after cleanup operation."""

    deployment_id: str
    resources_deleted: int = 0
    resources_failed: int = 0
    details: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
