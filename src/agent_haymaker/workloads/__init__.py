"""Workload base classes and interfaces.

This module defines the universal workload interface that all
workload implementations must inherit from.
"""

from .base import WorkloadBase
from .models import DeploymentConfig, DeploymentState, DeploymentStatus, WorkloadManifest
from .platform import Platform
from .registry import WorkloadRegistry

__all__ = [
    "WorkloadBase",
    "Platform",
    "DeploymentState",
    "DeploymentStatus",
    "DeploymentConfig",
    "WorkloadManifest",
    "WorkloadRegistry",
]
