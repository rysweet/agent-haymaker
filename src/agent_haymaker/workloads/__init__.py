"""Workload base classes and interfaces.

This module defines the universal workload interface that all
workload implementations must inherit from.
"""

from .base import WorkloadBase
from .models import DeploymentConfig, DeploymentState, WorkloadManifest
from .registry import WorkloadRegistry

__all__ = [
    "WorkloadBase",
    "DeploymentState",
    "DeploymentConfig",
    "WorkloadManifest",
    "WorkloadRegistry",
]
