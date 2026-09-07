"""Shared CLI helpers for the package entry points (multi-project selection).

Every path in this package resolves relative to the current working directory
(``ROOT_DIR = Path(".")`` in :mod:`ai_vt_singer`), so *selecting a project is a matter of
changing into that project's directory*. Each project is a directory containing its own
``config.toml`` (plus ``data/``, ``songs/``, ``setlists/``, ``images/``, ``out/``, ...);
the existing Neuro Twins project *is* the repository root.

This module provides a single, uniform way for entry points to accept a
``--project <dir>`` option and ``chdir`` into it before any project-relative work
happens. Because the change happens before :func:`ai_vt_singer.get_project` is first called
(it is lazy and cached), ``get_project()`` reads the right project's ``config.toml``,
and all the CWD-relative constants / ``project.*`` paths resolve under it automatically.

Usage (identical in every entry point)::

    import sys
    from ai_vt_singer.cli import chdir_to_project

    def my_command() -> None:
        remaining = chdir_to_project()   # honours --project <dir>; returns the rest
        ...                              # parse positional args from `remaining`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: The CLI option that selects which project to operate on.
PROJECT_FLAG = "--project"


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


def chdir_to_project(argv: list[str] | None = None) -> list[str]:
    """Parse ``argv`` for ``--project <dir>`` and ``chdir`` into it if present.

    Because all project paths are CWD-relative, changing directory is enough to select
    the project: ``config.toml``, ``data/``, ``songs/``, ``out/``, etc. all resolve under
    the new CWD, and :func:`ai_vt_singer.get_project` reads ``config.toml`` from it. When no
    ``--project`` is given this is a no-op and the current directory is used (the existing
    single-project behaviour).

    Args:
        argv: The arguments to scan. Defaults to ``sys.argv[1:]``.

    Returns:
        The arguments with the ``--project`` option removed, so the caller can parse its
        own positional arguments from them.

    Raises:
        SystemExit: If ``--project`` is given without a value, or the directory does not
            exist / is not a directory.
    """
    if argv is None:
        argv = sys.argv[1:]

    project_dir, remaining = _parse_project(argv)
    if project_dir is None:
        return remaining

    # Resolve to an absolute path *before* chdir so a relative --project isn't
    # re-interpreted against the new CWD.
    project_dir = project_dir.expanduser().resolve()
    if not project_dir.is_dir():
        raise SystemExit(f"error: project directory '{project_dir}' does not exist or is not a directory")
    if (project_dir / "config.toml").is_file():
        os.chdir(project_dir)
    else:
        raise SystemExit(f"error: project directory '{project_dir}' has no config.toml")
    return remaining
