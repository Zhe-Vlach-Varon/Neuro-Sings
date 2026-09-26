"""Operations on a project's generated output tree (``out/``).

Two user-facing commands live here. Both act on the *already-generated* ``out/`` folder —
they neither generate nor sync anything:

* :func:`clear_out` — delete everything under the project's output root.
* :func:`copy_out`  — copy the albums tree (or one preset group) into a single local folder,
  merging the official and unofficial releases together.

Both are project-agnostic: every path is resolved through :func:`~ai_vt_singer.get_project`,
so selecting a project is just ``cd``-ing into it (or passing ``--project <name>``).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from loguru import logger

from . import get_project
from .cli import chdir_to_project
from .run import get_presets_for_group, load_config
from .utils import format_logger


def clear_out() -> None:
    """Delete all generated output for the active project (the whole ``out/`` tree).

    Removes the project's output root — which contains both ``unofficial_releases/`` and
    ``official_releases/`` — so a fresh ``albums-generate`` / ``songs-generate`` starts clean.

    Safety: refuses to run unless the resolved output root is a *proper subdirectory* of the
    project directory, so a misconfigured ``out-root`` (e.g. ``"."`` or an absolute path outside
    the project) can never wipe the project itself.
    """
    chdir_to_project()
    project = get_project()
    format_logger(log_file=project.logs_dir / "generation.log")

    out_root = Path(project.out_root).expanduser().resolve()
    project_root = Path.cwd().resolve()

    if not out_root.exists():
        logger.info(f"[OUT] Nothing to clear: {out_root} does not exist")
        return
    if not out_root.is_dir():
        logger.error(f"[OUT] Refusing to delete '{out_root}': it is not a directory")
        sys.exit(1)
    # Guard against wiping the project itself (or anything outside of it).
    if out_root == project_root or not out_root.is_relative_to(project_root):
        logger.error(
            f"[OUT] Refusing to delete '{out_root}': the output root must be a subdirectory "
            f"of the project directory '{project_root}'."
        )
        sys.exit(1)

    n_files = sum(1 for p in out_root.rglob("*") if p.is_file() or p.is_symlink())
    logger.info(f"[OUT] Clearing output folder {out_root} ({n_files} files)")
    shutil.rmtree(out_root)
    logger.success(f"[OUT] Cleared output folder: {out_root}")


def _copy_tree(src_dir: Path, dest_root: Path) -> int:
    """Copy every file under ``src_dir`` into ``dest_root``, preserving relative structure.

    Symlinks are dereferenced (the real file content is copied), so the destination becomes a
    standalone tree with no links back into ``out/``. Broken symlinks are skipped with a warning
    instead of aborting the whole copy.

    Args:
        src_dir: Source directory to copy from.
        dest_root: Destination root; each file lands at ``dest_root / <relative path>``.

    Returns:
        int: Number of files copied.
    """
    if not src_dir.is_dir():
        return 0
    copied = 0
    for path in sorted(src_dir.rglob("*")):
        # Regular files and symlinks (valid or broken). Directories are created on demand below.
        if not (path.is_symlink() or path.is_file()):
            continue
        target = dest_root / path.relative_to(src_dir)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)  # follows symlinks; raises FileNotFoundError if broken
            copied += 1
        except (FileNotFoundError, OSError) as e:
            logger.warning(f"[COPY] Skipping {path}: {e}")
    return copied


def copy_out() -> None:
    """Copy the albums tree or a preset group's output into one local folder.

    Merges the official and unofficial releases into a single file tree under the destination,
    dereferencing symlinks so the result is self-contained real files (no links back to ``out/``).

    Usage::

        copy-out <albums|<group>> <dest-folder> [--project <name>]

    * ``albums`` — copies every album from both releases into ``<dest>/<Album>/...``.
    * a group name (e.g. ``zvv_sort``, ``original_sort``) — copies that group's preset folders
      from both releases into ``<dest>/<preset-path>/...`` (the redundant top-level group folder
      is dropped, since the group was already named as the selector).

    Raises:
        SystemExit: If arguments are missing, the group matches no preset, or nothing to copy exists.
    """
    remaining = chdir_to_project()
    what = remaining[0] if len(remaining) >= 1 else None
    dest = remaining[1] if len(remaining) >= 2 else None

    if not what or not dest:
        logger.error("Usage: copy-out <albums|<group>> <dest-folder> [--project <name>]")
        sys.exit(1)

    project = get_project()
    format_logger(log_file=project.logs_dir / "generation.log")
    dest_root = Path(dest).expanduser().resolve()

    # Build the list of (source dir, destination subdir) pairs to merge.
    sources: list[tuple[Path, Path]] = []
    if what == "albums":
        for release in (project.out_unofficial, project.out_official):
            sources.append((release / "albums", Path(".")))
    else:
        config = load_config()[0]
        try:
            presets = get_presets_for_group(config, what)
        except ValueError as e:
            logger.error(f"[COPY] {e}")
            sys.exit(1)
        for p in presets:
            group = p.get("group")
            path = Path(p["path"])
            # On-disk location includes the group prefix; destination drops it (already selected).
            src_rel = Path(group) / path if group else path
            for release in (project.out_unofficial, project.out_official):
                sources.append((release / src_rel, path))

    existing = [(src, sub) for src, sub in sources if src.is_dir()]
    if not existing:
        logger.error(
            f"[COPY] No output found to copy (looked under '{project.out_root}'). "
            f"Run 'albums-generate' and/or 'songs-generate' first."
        )
        sys.exit(1)

    dest_root.mkdir(parents=True, exist_ok=True)
    total = 0
    for src, sub in existing:
        dest_dir = dest_root if str(sub) == "." else dest_root / sub
        n = _copy_tree(src, dest_dir)
        total += n
        logger.info(f"[COPY] {src} -> {dest_dir} ({n} files)")

    logger.success(f"[COPY] Copied {total} file(s) into {dest_root}")


if __name__ == "__main__":
    copy_out()
