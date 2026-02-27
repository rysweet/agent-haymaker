"""Workload Registry - Discovers and manages workload implementations.

The registry is responsible for:
1. Discovering installed workloads (via entry points)
2. Loading workload manifests from repos/directories
3. Installing workloads from git repos
4. Providing workload instances to the CLI/API
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from .base import WorkloadBase
from .models import WorkloadManifest
from .platform import Platform

_logger = logging.getLogger(__name__)


class WorkloadRegistry:
    """Registry for discovering and managing workloads.

    Workloads can be:
    1. Installed Python packages (discovered via entry points)
    2. Local directories with workload.yaml
    3. Git repositories (cloned and installed on demand)
    """

    # Entry point group for workload discovery
    ENTRY_POINT_GROUP = "agent_haymaker.workloads"

    def __init__(self, platform: Platform | None = None) -> None:
        """Initialize the registry.

        Args:
            platform: Platform instance to inject into workloads
        """
        self._platform = platform
        self._workloads: dict[str, type[WorkloadBase]] = {}

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
                    _logger.warning("Failed to load workload %s: %s", ep.name, e, exc_info=True)

        except Exception as e:
            _logger.warning("Failed to discover workloads: %s", e, exc_info=True)

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
            ValueError: If installation fails or manifest source is invalid
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
                _logger.debug("git clone stderr: %s", result.stderr)
                raise ValueError("Failed to clone repository: git returned non-zero exit code")

            # Load manifest
            manifest = self.load_manifest(tmpdir)

            # Install the package
            if manifest.package:
                source_raw = manifest.package.get("source", ".")
                # Resolve relative paths against the clone directory
                source_path = (Path(tmpdir) / source_raw).resolve()

                # Reject any source that escapes the clone directory
                tmpdir_resolved = Path(tmpdir).resolve()
                if not source_path.is_relative_to(tmpdir_resolved):
                    raise ValueError(
                        f"Manifest 'source' path escapes the clone directory: {source_raw!r}"
                    )

                # Reject URLs or non-local-path values (prevent URL injection)
                if "://" in source_raw or source_raw.startswith(("http:", "https:", "ftp:")):
                    raise ValueError(
                        f"Manifest 'source' must be a local path, not a URL: {source_raw!r}"
                    )

                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", str(source_path)],
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                except subprocess.TimeoutExpired:
                    raise ValueError("pip install timed out after 300 seconds") from None
                if result.returncode != 0:
                    _logger.debug("pip install stderr: %s", result.stderr)
                    raise ValueError("Failed to install package: pip returned non-zero exit code")
            else:
                _logger.warning(
                    "Workload %s has no package config, skipping pip install",
                    manifest.name,
                )

            manifest_name = manifest.name

        # Discover after temp dir cleanup (safe for imports)
        self.discover_workloads()

        return manifest_name

    def install_from_path(self, path: Path | str) -> str:
        """Install a workload from a local directory.

        Args:
            path: Path to workload directory

        Returns:
            Name of the installed workload

        Raises:
            ValueError: If path is not a directory
        """
        path = Path(path).resolve()
        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")
        manifest = self.load_manifest(path)

        # Install as editable package
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", str(path)],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("pip install timed out after 300 seconds") from None
        if result.returncode != 0:
            _logger.debug("pip install stderr: %s", result.stderr)
            raise ValueError("Failed to install package: pip returned non-zero exit code")

        # Re-discover
        self.discover_workloads()

        return manifest.name

    def register_workload(self, name: str, workload_class: type[WorkloadBase]) -> None:
        """Manually register a workload class.

        Useful for testing or programmatic registration.

        Args:
            name: Workload name
            workload_class: Workload class to register
        """
        self._workloads[name] = workload_class
