"""Azure CLI wrapper with shared utilities.

Provides a safe subprocess wrapper for Azure CLI commands and
input validation for Azure resource names.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

_logger = logging.getLogger(__name__)

# Azure resource name pattern: lowercase alphanumeric + hyphens, 3-63 chars
_RESOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


def find_az_binary() -> str | None:
    """Find the Azure CLI binary in well-known locations."""
    for candidate in [
        Path.home() / "bin" / "az",
        Path("/usr/local/bin/az"),
    ]:
        if candidate.exists():
            return str(candidate)
    return shutil.which("az")


def run_az(
    args: list[str],
    timeout: int = 120,
    stdin_data: str | None = None,
) -> tuple[int, str, str]:
    """Run an Azure CLI command and return (returncode, stdout, stderr).

    Uses subprocess with list arguments (no shell=True) to prevent injection.

    Args:
        args: Azure CLI arguments (e.g. ["account", "show"]).
        timeout: Command timeout in seconds.
        stdin_data: Optional data to pipe via stdin (avoids secrets in argv).

    Returns:
        Tuple of (returncode, stdout, stderr).
    """
    az_path = find_az_binary()
    if az_path is None:
        return 127, "", "Azure CLI (az) not found. Install: https://aka.ms/installazurecli"

    cmd = [az_path] + args + ["--output", "json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_data,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "Azure CLI (az) not found."
    except subprocess.TimeoutExpired:
        return 124, "", f"Azure CLI command timed out after {timeout}s"


def validate_resource_name(name: str, field: str = "name") -> str:
    """Validate and normalize an Azure resource name.

    Args:
        name: The resource name to validate
        field: Field name for error messages

    Returns:
        Normalized (lowercased, underscore-to-hyphen) name

    Raises:
        ValueError: If name is invalid
    """
    normalized = name.lower().replace("_", "-")
    if not _RESOURCE_NAME_PATTERN.match(normalized):
        raise ValueError(
            f"Invalid Azure resource {field}: {name!r}. "
            "Must be 3-63 chars, lowercase alphanumeric and hyphens only."
        )
    return normalized


def sanitize_az_error(stderr: str) -> str:
    """Sanitize Azure CLI stderr for user-facing error messages.

    Removes subscription IDs, tenant IDs, and correlation IDs.
    """
    # Remove subscription/tenant GUIDs
    sanitized = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "<redacted>",
        stderr,
    )
    # Truncate to first 500 chars
    if len(sanitized) > 500:
        sanitized = sanitized[:500] + "..."
    return sanitized.strip()
