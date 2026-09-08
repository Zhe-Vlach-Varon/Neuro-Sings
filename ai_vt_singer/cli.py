"""Shared CLI helpers for the package entry points (multi-project selection).

Every path in this package resolves relative to the current working directory
(``ROOT_DIR = Path(".")`` in :mod:`ai_vt_singer`), so *selecting a project is a matter of
changing into that project's directory*. Each project is a directory containing its own
``config.toml`` (plus ``data/``, ``songs/``, ``setlists/``, ``images/``, ``out/``, ...);
the existing Neuro Twins project *is* the repository root.

This module provides a single, uniform way for entry points to accept a
``--project <name-or-dir>`` option and ``chdir`` into it before any project-relative work
happens. Because the change happens before :func:`ai_vt_singer.get_project` is first called
(it is lazy and cached), ``get_project()`` reads the right project's ``config.toml``,
and all the CWD-relative constants / ``project.*`` paths resolve under it automatically.

Usage (identical in every entry point)::

    import sys
    from ai_vt_singer.cli import chdir_to_project

    def my_command() -> None:
        remaining = chdir_to_project()   # honours --project <name-or-dir>; returns the rest
        ...                              # parse positional args from `remaining`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: The CLI option that selects which project to operate on.
PROJECT_FLAG = "--project"

#: The directory (relative to the repo root / CWD) where named projects live.
PROJECTS_DIR = Path("projects")


def _parse_project(argv: list[str]) -> tuple[Path | None, list[str]]:
    """Split the ``--project <dir>`` option out of ``argv``.

    Accepts both ``--project <dir>`` and ``--project=<dir>``, in any position.

    Args:
        argv: The arguments to scan.

    Returns:
        A tuple ``(project_dir, remaining)`` where ``project_dir`` is the value of
        ``--project`` (or ``None`` if absent) and ``remaining`` is ``argv`` with the
        option and its value removed (order otherwise preserved).

    Raises:
        SystemExit: If ``--project`` is given without a directory argument.
    """
    remaining: list[str] = []
    project_dir: Path | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == PROJECT_FLAG:
            if i + 1 >= len(argv):
                raise SystemExit(f"error: {PROJECT_FLAG} requires a directory argument")
            project_dir = Path(argv[i + 1])
            i += 2
        elif arg.startswith(PROJECT_FLAG + "="):
            project_dir = Path(arg.split("=", 1)[1])
            i += 1
        else:
            remaining.append(arg)
            i += 1
    return project_dir, remaining


def _is_project_dir(path: Path) -> bool:
    """Return True if *path* is a directory containing a ``config.toml``."""
    return path.is_dir() and (path / "config.toml").is_file()


def _resolve_project(value: Path) -> Path | None:
    """Resolve *value* to a valid project directory.

    Tries in order:
    1. The literal path (resolved against CWD).
    2. ``projects/<value>`` (so bare names like ``neuro`` work from the repo root).

    Returns the resolved path, or ``None`` if no valid project was found.
    """
    # 1. Literal path as given.
    candidate = value.expanduser().resolve()
    if _is_project_dir(candidate):
        return candidate

    # 2. Assume it's a name inside projects/.
    candidate = (PROJECTS_DIR / value).expanduser().resolve()
    if _is_project_dir(candidate):
        return candidate

    return None


def _list_available_projects() -> list[Path]:
    """Return sorted subdirectories of ``projects/`` that contain a ``config.toml``.

    Directories whose name starts with ``_`` (e.g. ``_template``) are excluded.
    """
    projects_root = PROJECTS_DIR.resolve()
    if not projects_root.is_dir():
        return []
    return sorted(d for d in projects_root.iterdir() if not d.name.startswith("_") and _is_project_dir(d))


def chdir_to_project(argv: list[str] | None = None) -> list[str]:
    """Parse ``argv`` for ``--project <name-or-dir>`` and ``chdir`` into it if present.

    Because all project paths are CWD-relative, changing directory is enough to select
    the project: ``config.toml``, ``data/``, ``songs/``, ``out/``, etc. all resolve under
    the new CWD, and :func:`ai_vt_singer.get_project` reads ``config.toml`` from it. When no
    ``--project`` is given this is a no-op and the current directory is used (the existing
    single-project behaviour).

    The project value may be:

    - A bare name (e.g. ``neuro``) — resolved as ``projects/neuro``.
    - A relative or absolute path to a directory containing ``config.toml``.

    Args:
        argv: The arguments to scan. Defaults to ``sys.argv[1:]``.

    Returns:
        The arguments with the ``--project`` option removed, so the caller can parse its
        own positional arguments from them.

    Raises:
        SystemExit: If the project cannot be resolved to a valid project directory.
    """
    if argv is None:
        argv = sys.argv[1:]

    project_dir, remaining = _parse_project(argv)
    if project_dir is None:
        # No --project flag: if CWD already has a config.toml, we're good.
        # Otherwise, auto-detect: if exactly one project exists, use it.
        if _is_project_dir(Path.cwd()):
            return remaining
        available = _list_available_projects()
        if len(available) == 1:
            os.chdir(available[0])
            return remaining
        names = ", ".join(p.name for p in available) if available else "none"
        raise SystemExit(
            f"error: no config.toml in current directory and cannot auto-detect a project.\n"
            f"  available projects: {names}\n"
            f"  use '--project <name>' to select one explicitly."
        )

    resolved = _resolve_project(project_dir)
    if resolved is not None:
        os.chdir(resolved)
        return remaining

    # Idempotency: if we can't resolve the name but we're already inside a valid
    # project directory (CWD has a config.toml), treat it as a no-op. This handles
    # the case where chdir_to_project() is called multiple times in a call chain
    # (e.g. drive_push → setlists_push) and the CWD has already been changed.
    if _is_project_dir(Path.cwd()):
        return remaining

    # Build a helpful error message.
    available = _list_available_projects()
    lines = [f"error: could not resolve project '{project_dir}'"]
    if available:
        names = ", ".join(p.name for p in available)
        lines.append(f"  available projects: {names}")
    else:
        lines.append(f"  no projects found in '{PROJECTS_DIR}/'")
    lines.append("  (a project directory must contain a config.toml)")
    raise SystemExit("\n".join(lines))
