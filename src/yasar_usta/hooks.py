"""Per-project lifecycle hooks, dispatched as a SUBPROCESS in the project's own
venv so the hub never imports project packages.

Contract: the project ships a ``yasar_hooks.py`` runnable by its venv python:
    <project_venv_python> yasar_hooks.py <phase> --context <json>
where <phase> is 'pre_boot' or 'on_exit'. The JSON context carries what the
old in-process hook read from the project object.
"""
from __future__ import annotations

import json
import logging
import subprocess

logger = logging.getLogger("yasar_usta.hooks")


def _script_paths(project) -> list:
    paths = []
    for tgt in getattr(project, "targets", []) or []:
        for arg in getattr(tgt, "command", []) or []:
            if isinstance(arg, str) and arg.lower().endswith(".py"):
                paths.append(arg)
    return paths


def build_hook_command(project, phase: str, extra: dict) -> list | None:
    """Argv list (never a shell string — Windows backslash JSON) or None if the
    project declares no hook."""
    venv_python = getattr(project, "venv_python", None)
    hook_path = getattr(project, "hook_path", None)
    if not (venv_python and hook_path):
        return None
    context = {"project_id": project.id, "script_paths": _script_paths(project)}
    context.update(extra or {})
    return [venv_python, hook_path, phase, "--context", json.dumps(context)]


def run_hook_subprocess(project, phase: str, extra: dict) -> int | None:
    """Spawn the project's hook. Returns rc, or None if no hook declared.
    pre_boot surfaces failure (raises); on_exit is fail-soft."""
    cmd = build_hook_command(project, phase, extra)
    if cmd is None:
        return None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        logger.error("hook %s for %s failed to spawn: %s", phase, project.id, e)
        if phase == "pre_boot":
            raise
        return None
    stdout = getattr(result, "stdout", None) or ""
    stderr = getattr(result, "stderr", None) or ""
    if stdout:
        logger.info("[hook %s/%s] %s", project.id, phase, stdout.strip())
    if result.returncode != 0:
        logger.error("[hook %s/%s] rc=%s stderr=%s", project.id, phase,
                     result.returncode, stderr.strip())
        if phase == "pre_boot":
            raise RuntimeError(f"pre_boot hook for {project.id} failed rc={result.returncode}")
    return result.returncode


def run_pre_boot(project) -> None:
    """Back-compat name used by hub.run(). Subprocess dispatch."""
    run_hook_subprocess(project, "pre_boot", extra={})
