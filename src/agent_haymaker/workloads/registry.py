"""Workload Registry - Discovers and manages workload implementations.

The registry is responsible for:
1. Discovering installed workloads (via entry points)
2. Loading workload manifests from repos/directories
3. Installing workloads from git repos
4. Providing workload instances to the CLI/API
"""

import importlib
import logging
import subprocess
import tempfile
import traceback
from pathlib import Path
from typing import Any

import yaml

from .base import WorkloadBase
from .models import WorkloadManifest


class WorkloadRegistry:
    """Registry for discovering and managing workloads.

    Workloads can be:
    1. Installed Python packages (discovered via entry points)
    2. Local directories with workload.yaml
    3. Git repositories (cloned and installed on demand)
    """

    # Entry point group for workload discovery
    ENTRY_POINT_GROUP = "agent_haymaker.workloads"

    def __init__(self, platform: Any = None) -> None:
        """Initialize the registry.

        Args:
            platform: Platform instance to inject into workloads
        """
        self._platform = platform
        self._workloads: dict[str, type[WorkloadBase]] = {}
        self._manifests: dict[str, WorkloadManifest] = {}

    def discover_workloads(self) -> dict[str, type[WorkloadBase]]:
        """Discover all installed workloads via entry points.

        Workloads register themselves in pyproject.toml:
            [project.entry-points."agent_haymaker.workloads"]
            m365-knowledge-worker = "haymaker_m365_workloads:M365KnowledgeWorkerWorkload"

        Returns:
            Dict mapping workload names to workload classes
        """
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group=self.ENTRY_POINT_GROUP)

            for ep in eps:
                try:
                    workload_class = ep.load()
                    if isinstance(workload_class, type) and issubclass(
                        workload_class, WorkloadBase
                    ):
                        self._workloads[ep.name] = workload_class
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        "Failed to load workload %s: %s\n%s",
                        ep.name,
                        e,
                        traceback.format_exc(),
                    )

        except Exception as e:
            logging.getLogger(__name__).warning(
                "Failed to discover workloads: %s\n%s", e, traceback.format_exc()
            )

        return self._workloads

    def get_workload(self, name: str) -> WorkloadBase | None:
        """Get an instance of a workload by name.

        Args:
            name: Workload name

        Returns:
            Workload instance or None if not found
        """
        if not self._workloads:
            self.discover_workloads()

        workload_class = self._workloads.get(name)
        if workload_class:
            return workload_class(platform=self._platform)

        return None

    def list_workloads(self) -> list[str]:
        """List all available workload names.

        Returns:
            List of workload names
        """
        if not self._workloads:
            self.discover_workloads()

        return list(self._workloads.keys())

    def load_manifest(self, path: Path | str) -> WorkloadManifest:
        """Load workload manifest from a directory.

        Args:
            path: Path to directory containing workload.yaml

        Returns:
            Parsed WorkloadManifest

        Raises:
            FileNotFoundError: If workload.yaml doesn't exist
            ValueError: If manifest is invalid
        """
        path = Path(path)
        manifest_file = path / "workload.yaml"

        if not manifest_file.exists():
            raise FileNotFoundError(f"No workload.yaml found in {path}")

        with open(manifest_file) as f:
            data = yaml.safe_load(f)

        return WorkloadManifest(**data)

    def install_from_git(self, repo_url: str) -> str:
        """Install a workload from a git repository.

        Clones the repo, reads workload.yaml, and pip installs the package.

        Args:
            repo_url: Git repository URL

        Returns:
            Name of the installed workload

        Raises:
            ValueError: If installation fails
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Clone the repo
            try:
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", repo_url, tmpdir],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                raise ValueError("Git clone timed out after 120 seconds") from None
            if result.returncode != 0:
                raise ValueError(f"Failed to clone {repo_url}: {result.stderr}")

            # Load manifest
            manifest = self.load_manifest(tmpdir)

            # Install the package
            if manifest.package:
                source = manifest.package.get("source", tmpdir)
                try:
                    result = subprocess.run(
                        ["pip", "install", source],
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                except subprocess.TimeoutExpired:
                    raise ValueError("pip install timed out after 300 seconds") from None
                if result.returncode != 0:
                    raise ValueError(f"Failed to install package: {result.stderr}")
            else:
                logging.getLogger(__name__).warning(
                    "Workload %s has no package config, skipping pip install",
                    manifest.name,
                )

            # Re-discover workloads to pick up new one
            self.discover_workloads()

            return manifest.name

    def install_from_path(self, path: Path | str) -> str:
        """Install a workload from a local directory.

        Args:
            path: Path to workload directory

        Returns:
            Name of the installed workload
        """
        path = Path(path)
        manifest = self.load_manifest(path)

        # Install as editable package
        try:
            result = subprocess.run(
                ["pip", "install", "-e", str(path)],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("pip install timed out after 300 seconds") from None
        if result.returncode != 0:
            raise ValueError(f"Failed to install package: {result.stderr}")

        # Re-discover
        self.discover_workloads()

        return manifest.name

    def load_workload_class(self, entrypoint: str) -> type[WorkloadBase]:
        """Load a workload class from an entrypoint string.

        Args:
            entrypoint: "module.path:ClassName" format

        Returns:
            Workload class

        Raises:
            ImportError: If module can't be loaded
            AttributeError: If class doesn't exist
        """
        module_path, class_name = entrypoint.rsplit(":", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def register_workload(self, name: str, workload_class: type[WorkloadBase]) -> None:
        """Manually register a workload class.

        Useful for testing or programmatic registration.

        Args:
            name: Workload name
            workload_class: Workload class to register
        """
        self._workloads[name] = workload_class
