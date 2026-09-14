import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loguru import logger

from . import get_project
from .cli import chdir_to_project
from .polars_utils import load_dates, load_db
from .utils import format_logger

# Path constants for local and remote Paths
REMOTE_INPUT_PREFIX = Path("_inputs")
REMOTE_OUT_PREFIX = Path("out")

# rclone command
RCLONE_SYNC = "rclone sync"

# rclone sync options
# COMMON_OPTIONS = " --stats-file-name-length 0 --progress --transfers 2 --track-renames"
COMMON_OPTIONS = " --stats-file-name-length 0 --progress --track-renames --checksum"
DRIVE_OPTIONS = " --drive-use-trash=false"
CHECK_OPTIONS = " --dry-run"
PURGE_OPTIONS = " --max-transfer=1B"
remote_links = True
local_links = True
LINK_OPTIONS =  " --skip-links" if remote_links and local_links else (" --copy-links" if local_links else "")

verb = False
V = " -v" if verb else ""

dryrun = False
DR = CHECK_OPTIONS if dryrun else ""

# test run, copy to local folder instead of drive
TR = False

# rclone complete commands
DRIVE_RCLONE_COMMAND = f"{RCLONE_SYNC}{COMMON_OPTIONS}{DRIVE_OPTIONS}{V}{DR}"

LOCAL_TEST_IN_DIR = Path("temp")
LOCAL_TEST_OUT_PUB_DIR = Path("temp_public")
LOCAL_TEST_OUT_PRV_DIR = Path("temp_private")

RCLONE_BACKEND_COMMAND = f"rclone backend shortcut{V}{DR}"


def _rclone_command(command: str) -> int:
    """Run an rclone command, logging it. Returns the process exit code."""
    logger.info(command)
    return subprocess.run(command, shell=True, check=False).returncode


def _rclone_captured(command: str) -> tuple[int, str]:
    """Run an rclone command, logging it. Returns (exit code, stripped stderr)."""
    logger.info(command)
    result = subprocess.run(command, shell=True, capture_output=True, text=True, check=False)
    return result.returncode, (result.stderr or "").strip()


def _rclone(command: str, error_label: str) -> None:
    """Run an rclone command, logging it and exiting on failure."""
    if _rclone_command(command):
        logger.error(error_label)
        sys.exit(1)


# Each shortcut is one network round-trip to GDrive; keep the pool modest to avoid quota pressure.
SHORTCUT_MAX_WORKERS = 4


def _remove_broken_shortcuts(out_dir: Path, dest: str, dir_prefix: str) -> None:
    """Check for broken GDrive shortcuts under out_dir and remove them.

    A shortcut is broken if its target file no longer exists on the remote.
    Uses a single recursive listing (rclone lsjson -R) to check all targets at once.
    """
    base = out_dir.resolve()
    files = [f for f in base.rglob("*.mp3") if f.is_symlink()]
    if not files:
        return

    # Collect all expected target paths (relative to base)
    expected_targets: set[str] = set()
    for file in files:
        expected_targets.add(file.resolve().relative_to(base).as_posix())

    # Get a single recursive listing of all files on the remote
    # The remote layout is flat under out/ (albums + preset folders), not under out/<release_name>/
    remote_dir = f"{dest}{dir_prefix}{REMOTE_OUT_PREFIX}"
    cmd = f'rclone lsjson -R "{remote_dir}"'
    logger.info(cmd)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.warning(f"Failed to list remote files for broken shortcut check: {result.stderr.strip()}")
        return

    # Build a set of existing file paths from the listing
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse rclone lsjson output: {e}")
        return

    existing: set[str] = set()
    for entry in entries:
        if not entry.get("IsDir", False):
            existing.add(entry["Path"])

    # Find broken shortcuts: targets that don't exist on remote
    broken: list[Path] = []
    for file in files:
        target_rel = file.resolve().relative_to(base).as_posix()
        if target_rel not in existing:
            broken.append(file)

    if not broken:
        return

    logger.info(f"Found {len(broken)} broken shortcuts, removing them")
    for file in broken:
        shortcut_remote = f"{dest}{dir_prefix}{REMOTE_OUT_PREFIX / file.relative_to(base)}"
        _rclone(f'rclone delete "{shortcut_remote}"', f"failed to remove broken shortcut for {file}")


# rclone's error when a file already occupies the shortcut destination path, e.g.:
#   Failed to backend: command "shortcut" failed: not overwriting shortcut target: existing file
EXISTING_SHORTCUT_ERROR = "not overwriting shortcut target"


def _remote_file_id(remote_path: str) -> str | None:
    """Return the ID of a single remote file via `rclone lsjson`, or None if it can't be listed."""
    result = subprocess.run(f'rclone lsjson "{remote_path}"', shell=True, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    for entry in entries:
        if not entry.get("IsDir", False):
            return entry.get("ID")
    return None


def _existing_shortcut_points_to_same_target(shortcut_remote: str, source_remote: str) -> bool:
    """True if the file at shortcut_remote is a GDrive shortcut pointing to the same target as source_remote.

    rclone reports a GDrive shortcut's ID as "<shortcut-id>\\t<target-id>"; regular files have a single ID.
    """
    shortcut_id = _remote_file_id(shortcut_remote)
    source_id = _remote_file_id(source_remote)
    if not shortcut_id or not source_id:
        return False
    return source_id in shortcut_id.split("\t")


def _create_drive_shortcuts(out_dir: Path, dest: str, dir_prefix: str, error_label: str, max_workers: int = SHORTCUT_MAX_WORKERS) -> None:
    """Create GDrive shortcuts for all symlinked .mp3 files under out_dir.

    The calls are independent → run through a small thread pool instead of sequentially
    (thousands of symlinks would otherwise mean thousands of serial round-trips).

    A shortcut that already exists at its destination pointing to the same target file is kept
    as-is and counted, so re-runs are idempotent (rclone refuses to overwrite an existing
    shortcut: "not overwriting shortcut target: existing file"). Any other rclone error still
    fails fast: the pending ones are cancelled and it exits 1.

    Before creating shortcuts, the target directory structure is created on the remote
    (sequentially, parents before children) to avoid a race condition where multiple
    workers creating shortcuts in the same non-existent directory produce duplicate folders.

    Args:
        out_dir (Path): Local output dir containing the symlinked .mp3 files.
        dest (str): Remote destination prefix (e.g. "DriveName:" or "./").
        dir_prefix (str): Extra local path prefix for TR test runs.
        error_label (str): Error message logged before exiting on failure.
        max_workers (int, optional): Concurrent shortcut creations. Defaults to SHORTCUT_MAX_WORKERS.

    Raises:
        SystemExit: If any rclone call fails with an unexpected error, after cancelling pending work.
    """
    base = out_dir.resolve()
    files = [f for f in base.rglob("*.mp3") if f.is_symlink()]

    if not files:
        return

    _remove_broken_shortcuts(out_dir, dest, dir_prefix)

    # (local file, rclone command, full source remote path, full shortcut remote path)
    commands: list[tuple[Path, str, str, str]] = []
    parent_dirs: set[Path] = set()
    remote_prefix = f"{dest}{dir_prefix}"
    for file in files:
        source_path = REMOTE_OUT_PREFIX / file.resolve().relative_to(base)
        shortcut_path = REMOTE_OUT_PREFIX / file.relative_to(base)
        parent = (file.relative_to(base)).parent
        if str(parent) != ".":
            parent_dirs.add(parent)
        cmd = f'{RCLONE_BACKEND_COMMAND} {remote_prefix} "{source_path}" "{shortcut_path}"'
        commands.append((file, cmd, f"{remote_prefix}{source_path}", f"{remote_prefix}{shortcut_path}"))

    # Create the directory structure on the remote first (sequentially, parents before
    # children) to avoid a race condition where multiple workers creating shortcuts in
    # the same non-existent directory produce duplicate folders.
    if parent_dirs:
        logger.info(f"Creating {len(parent_dirs)} directories on the remote before making shortcuts")
        for d in sorted(parent_dirs, key=lambda p: len(p.parts)):
            _rclone(
                f"rclone mkdir {dest}{dir_prefix}{REMOTE_OUT_PREFIX / d}",
                f"failed to create directory '{d}' on the remote",
            )

    def _run(item: tuple[Path, str, str, str]) -> tuple[tuple[Path, str, str, str], int, str]:
        # subprocess.run is fork+exec → safe to call from multiple threads (loguru too)
        code, stderr = _rclone_captured(item[1])
        return item, code, stderr

    failed_file: Path | None = None
    skipped_existing = 0
    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="shortcut")
    try:
        for (file, _cmd, source_remote, shortcut_remote), code, stderr in executor.map(_run, commands):
            if code == 0:
                continue
            # A previous run may have already created this exact shortcut. rclone refuses to
            # overwrite it; verify the existing file points to the same target and keep it.
            already_exists = (
                EXISTING_SHORTCUT_ERROR in stderr
                and _existing_shortcut_points_to_same_target(shortcut_remote, source_remote)
            )
            if already_exists:
                logger.debug(f"shortcut for {file} already exists pointing to the same target — skipping")
                skipped_existing += 1
                continue
            logger.error(f"rclone shortcut creation failed for {file} (exit code {code}): {stderr}")
            failed_file = file
            break
    finally:
        # Stop scheduling the rest; the ≤ max_workers calls already in flight finish on their own
        executor.shutdown(wait=False, cancel_futures=True)

    if failed_file is not None:
        logger.error(error_label)
        sys.exit(1)

    if skipped_existing:
        logger.info(f"kept {skipped_existing} existing shortcut(s) that already pointed to the same target")


def setlists_pull() -> None:
    chdir_to_project()
    project = get_project()
    format_logger(log_file=project.logs_dir / "sync.log")
    setlist_pull_command = f"{DRIVE_RCLONE_COMMAND} {project.drive_public}:{REMOTE_INPUT_PREFIX}/{project.setlists_dir} {project.setlists_dir}"
    _rclone(setlist_pull_command, "setlists pull failed")


def setlists_push() -> None:
    chdir_to_project()
    project = get_project()
    format_logger(log_file=project.logs_dir / "sync.log")
    public_dest = f"{project.drive_public}:" if not TR else f"{LOCAL_TEST_OUT_PUB_DIR}/"
    public_dir = f"{Path(project.drive_public)}/" if TR else ""
    setlist_push_command = f"{DRIVE_RCLONE_COMMAND} {project.setlists_dir} {public_dest}{public_dir}{REMOTE_INPUT_PREFIX}/{project.setlists_dir}"
    _rclone(setlist_push_command, "setlists push failed")


def drive_pull() -> None:
    chdir_to_project()
    project = get_project()
    format_logger(log_file=project.logs_dir / "sync.log")
    drive_pull_command = f"{DRIVE_RCLONE_COMMAND} {project.drive_source}: {LOCAL_TEST_IN_DIR}/{project.song_root.name}/{project.song_dirs['unofficialv3']}"
    _rclone(drive_pull_command, "drive pull failed")

# TODO command to apply my changes to unofficial archive metadata

def inputs_pull() -> None:
    chdir_to_project()
    project = get_project()
    format_logger(log_file=project.logs_dir / "sync.log")
    public_drive = project.drive_public
    private_drive = project.drive_private

    # public input files
    setlists_pull()

    _rclone(f"{DRIVE_RCLONE_COMMAND} {public_drive}:{REMOTE_INPUT_PREFIX}/{project.data_dir} {project.data_dir}", "drive pull failed: data")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {public_drive}:{REMOTE_INPUT_PREFIX}/{project.images_covers_dir.parent} {project.images_covers_dir.parent}", "drive pull failed: images")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {public_drive}:{REMOTE_INPUT_PREFIX}/{project.song_root / project.song_dirs['custom']} {project.song_root / project.song_dirs['custom']}", "drive pull failed: custom")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {public_drive}:{REMOTE_INPUT_PREFIX}/{project.song_root / project.song_dirs['unofficialv3']} {project.song_root / project.song_dirs['unofficialv3']}", "drive pull failed: unofficialV3")

    # private input files
    _rclone(f"{DRIVE_RCLONE_COMMAND} {private_drive}:{REMOTE_INPUT_PREFIX}/{project.song_root / project.song_dirs['official']} {project.song_root / project.song_dirs['official']}", "drive pull failed: official releases")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {private_drive}:{REMOTE_INPUT_PREFIX}/{project.song_root / project.song_dirs['copyright']} {project.song_root / project.song_dirs['copyright']}", "drive pull failed: copyright issues")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {private_drive}:{REMOTE_INPUT_PREFIX}/{project.fonts_dir} {project.fonts_dir}", "drive pull failed: fonts")

    logger.success("finished downloading input files from gdrive")


def drive_push() -> None:
    chdir_to_project()
    project = get_project()
    format_logger(log_file=project.logs_dir / "sync.log")
    public_drive = project.drive_public
    private_drive = project.drive_private
    public_dest = f"{public_drive}:" if not TR else f"{LOCAL_TEST_OUT_PUB_DIR}/"
    private_dest = f"{private_drive}:" if not TR else f"{LOCAL_TEST_OUT_PRV_DIR}/"
    public_dir = f"{Path(public_drive)}/" if TR else ""
    private_dir = f"{Path(private_drive)}/" if TR else ""

    # public input files
    setlists_push()

    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.data_dir} {public_dest}{public_dir}{REMOTE_INPUT_PREFIX}/{project.data_dir}", "drive push failed: data")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.images_covers_dir.parent} {public_dest}{public_dir}{REMOTE_INPUT_PREFIX}/{project.images_covers_dir.parent}", "drive push failed: images")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.song_root / project.song_dirs['custom']} {public_dest}{public_dir}{REMOTE_INPUT_PREFIX}/{project.song_root / project.song_dirs['custom']}", "drive push failed: custom")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.song_root / project.song_dirs['unofficialv3']} {public_dest}{public_dir}{REMOTE_INPUT_PREFIX}/{project.song_root / project.song_dirs['unofficialv3']}", "drive push failed: unofficialV3")

    # private input files
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.song_root / project.song_dirs['official']} {private_dest}{private_dir}{REMOTE_INPUT_PREFIX}/{project.song_root / project.song_dirs['official']}", "drive push failed: official releases")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.song_root / project.song_dirs['copyright']} {private_dest}{private_dir}{REMOTE_INPUT_PREFIX}/{project.song_root / project.song_dirs['copyright']}", "drive push failed: copyright issues")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.fonts_dir} {private_dest}{private_dir}{REMOTE_INPUT_PREFIX}/{project.fonts_dir}", "drive push failed: fonts")

    # public out files — albums (real files, no shortcuts)
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.out_unofficial / 'albums'} {public_dest}{public_dir}{REMOTE_OUT_PREFIX / 'albums'}", "drive push failed: public albums")
    # public out files — preset folders (symlinks → GDrive shortcuts)
    if not remote_links:
        _rclone(f"{DRIVE_RCLONE_COMMAND} --exclude 'albums/' {project.out_unofficial} {public_dest}{public_dir}{REMOTE_OUT_PREFIX}{LINK_OPTIONS}", "drive push failed: public preset folders")
    else:
        _create_drive_shortcuts(project.out_unofficial, public_dest, public_dir, "drive push failed: public out make GDrive shortcuts")

    # private out files — albums (real files, no shortcuts)
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.out_official / 'albums'} {private_dest}{private_dir}{REMOTE_OUT_PREFIX / 'albums'}", "drive push failed: private albums")
    # private out files — preset folders (symlinks → GDrive shortcuts)
    if not remote_links:
        _rclone(f"{DRIVE_RCLONE_COMMAND} --exclude 'albums/' {project.out_official} {private_dest}{private_dir}{REMOTE_OUT_PREFIX}{LINK_OPTIONS}", "drive push failed: private preset folders")
    else:
        _create_drive_shortcuts(project.out_official, private_dest, private_dir, "drive push failed: private out make GDrive shortcuts")

    logger.success("finished uploading to gdrive")


def dbs_sync() -> None:
    chdir_to_project()
    project = get_project()
    format_logger(log_file=project.logs_dir / "sync.log")
    FROM_DB = False
    db = load_db(FROM_DB)
    dates = load_dates(FROM_DB)

    db.write_csv(project.songs_csv)
    dates.write_csv(project.dates_csv)

    db.write_database("Songs", f"sqlite:///{project.songs_db}", if_table_exists="replace")
    dates.write_database("Dates", f"sqlite:///{project.songs_db}", if_table_exists="replace")
    logger.success(f"Synced versions of the databases, taking {'DB' if FROM_DB else 'CSV'} as source")
