import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loguru import logger

from . import LOG_DIR, get_project
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
    return os.system(command)


def _rclone(command: str, error_label: str) -> None:
    """Run an rclone command, logging it and exiting on failure."""
    if _rclone_command(command):
        logger.error(error_label)
        exit(1)


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
    remote_dir = f"{dest}{dir_prefix}{REMOTE_OUT_PREFIX / base.name}"
    cmd = f'rclone lsjson -R "{remote_dir}"'
    logger.info(cmd)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
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


def _create_drive_shortcuts(out_dir: Path, dest: str, dir_prefix: str, error_label: str, max_workers: int = SHORTCUT_MAX_WORKERS) -> None:
    """Create GDrive shortcuts for all symlinked .mp3 files under out_dir.

    The calls are independent → run through a small thread pool instead of sequentially
    (thousands of symlinks would otherwise mean thousands of serial round-trips).
    Fails fast like before: the first rclone error cancels the pending ones and exits 1.

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
        SystemExit: If any rclone call fails (exit code 1), after cancelling pending work.
    """
    base = out_dir.resolve()
    files = [f for f in base.rglob("*.mp3") if f.is_symlink()]

    if not files:
        return

    _remove_broken_shortcuts(out_dir, dest, dir_prefix)

    commands: list[tuple[Path, str]] = []
    parent_dirs: set[Path] = set()
    for file in files:
        source_drive_path = file.resolve().relative_to(base)
        shortcut_drive_path = file.relative_to(base)
        parent = shortcut_drive_path.parent
        if str(parent) != ".":
            parent_dirs.add(parent)
        cmd = (
            f"{RCLONE_BACKEND_COMMAND} {dest}{dir_prefix}"
            f" \"{REMOTE_OUT_PREFIX / source_drive_path}\""
            f" \"{REMOTE_OUT_PREFIX / shortcut_drive_path}\""
        )
        commands.append((file, cmd))

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

    def _run(item: tuple[Path, str]) -> tuple[Path, int]:
        file, cmd = item
        # os.system is fork+exec → safe to call from multiple threads (loguru too)
        return file, _rclone_command(cmd)

    failed_file: Path | None = None
    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="shortcut")
    try:
        for file, code in executor.map(_run, commands):
            if code != 0:
                logger.error(f"rclone shortcut creation failed for {file} (exit code {code})")
                failed_file = file
                break
    finally:
        # Stop scheduling the rest; the ≤ max_workers calls already in flight finish on their own
        executor.shutdown(wait=False, cancel_futures=True)

    if failed_file is not None:
        logger.error(error_label)
        exit(1)


def setlists_pull() -> None:
    chdir_to_project()
    format_logger(log_file=LOG_DIR / "sync.log")
    project = get_project()
    setlist_pull_command = f"{DRIVE_RCLONE_COMMAND} {project.drive_public}:{REMOTE_INPUT_PREFIX}/{project.setlists_dir} {project.setlists_dir}"
    _rclone(setlist_pull_command, "setlists pull failed")


def setlists_push() -> None:
    chdir_to_project()
    format_logger(log_file=LOG_DIR / "sync.log")
    project = get_project()
    public_dest = f"{project.drive_public}:" if not TR else f"{LOCAL_TEST_OUT_PUB_DIR}/"
    public_dir = f"{Path(project.drive_public)}/" if TR else ""
    setlist_push_command = f"{DRIVE_RCLONE_COMMAND} {project.setlists_dir} {public_dest}{public_dir}{REMOTE_INPUT_PREFIX}/{project.setlists_dir}"
    _rclone(setlist_push_command, "setlists push failed")


def drive_pull() -> None:
    chdir_to_project()
    format_logger(log_file=LOG_DIR / "sync.log")
    project = get_project()
    drive_pull_command = f"{DRIVE_RCLONE_COMMAND} {project.drive_source}: {LOCAL_TEST_IN_DIR}/{project.song_root.name}/unofficialV3"
    _rclone(drive_pull_command, "drive pull failed")

# TODO command to apply my changes to unofficial archive metadata

def inputs_pull() -> None:
    chdir_to_project()
    format_logger(log_file=LOG_DIR / "sync.log")
    project = get_project()
    public_drive = project.drive_public
    private_drive = project.drive_private

    # public input files
    setlists_pull()

    _rclone(f"{DRIVE_RCLONE_COMMAND} {public_drive}:{REMOTE_INPUT_PREFIX}/{project.data_dir} {project.data_dir}", "drive pull failed: data")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {public_drive}:{REMOTE_INPUT_PREFIX}/{project.images_covers_dir.parent} {project.images_covers_dir.parent}", "drive pull failed: images")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {public_drive}:{REMOTE_INPUT_PREFIX}/{project.song_root / 'custom'} {project.song_root / 'custom'}", "drive pull failed: custom")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {public_drive}:{REMOTE_INPUT_PREFIX}/{project.song_root / 'unofficialV3'} {project.song_root / 'unofficialV3'}", "drive pull failed: unofficialV3")

    # private input files
    _rclone(f"{DRIVE_RCLONE_COMMAND} {private_drive}:{REMOTE_INPUT_PREFIX}/{project.song_root / 'officially_released_songs'} {project.song_root / 'officially_released_songs'}", "drive pull failed: official releases")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {private_drive}:{REMOTE_INPUT_PREFIX}/{project.song_root / 'copyright_issues'} {project.song_root / 'copyright_issues'}", "drive pull failed: copyright issues")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {private_drive}:{REMOTE_INPUT_PREFIX}/{project.fonts_dir} {project.fonts_dir}", "drive pull failed: fonts")

    logger.success("finished downloading input files from gdrive")


def drive_push() -> None:
    chdir_to_project()
    format_logger(log_file=LOG_DIR / "sync.log")
    project = get_project()
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
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.song_root / 'custom'} {public_dest}{public_dir}{REMOTE_INPUT_PREFIX}/{project.song_root / 'custom'}", "drive push failed: custom")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.song_root / 'unofficialV3'} {public_dest}{public_dir}{REMOTE_INPUT_PREFIX}/{project.song_root / 'unofficialV3'}", "drive push failed: unofficialV3")

    # private input files
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.song_root / 'officially_released_songs'} {private_dest}{private_dir}{REMOTE_INPUT_PREFIX}/{project.song_root / 'officially_released_songs'}", "drive push failed: official releases")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.song_root / 'copyright_issues'} {private_dest}{private_dir}{REMOTE_INPUT_PREFIX}/{project.song_root / 'copyright_issues'}", "drive push failed: copyright issues")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.fonts_dir} {private_dest}{private_dir}{REMOTE_INPUT_PREFIX}/{project.fonts_dir}", "drive push failed: fonts")

    # public out files — albums (real files, no shortcuts)
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.out_unofficial / 'albums'} {public_dest}{public_dir}{REMOTE_OUT_PREFIX / 'albums'}", "drive push failed: public albums")
    # public out files — preset folders (symlinks → GDrive shortcuts)
    _rclone(f"{DRIVE_RCLONE_COMMAND} --exclude 'albums/' {project.out_unofficial} {public_dest}{public_dir}{REMOTE_OUT_PREFIX}{LINK_OPTIONS}", "drive push failed: public preset folders")
    if remote_links:
        _create_drive_shortcuts(project.out_unofficial, public_dest, public_dir, "drive push failed: public out make GDrive shortcuts")

    # private out files — albums (real files, no shortcuts)
    _rclone(f"{DRIVE_RCLONE_COMMAND} {project.out_official / 'albums'} {private_dest}{private_dir}{REMOTE_OUT_PREFIX / 'albums'}", "drive push failed: private albums")
    # private out files — preset folders (symlinks → GDrive shortcuts)
    _rclone(f"{DRIVE_RCLONE_COMMAND} --exclude 'albums/' {project.out_official} {private_dest}{private_dir}{REMOTE_OUT_PREFIX}{LINK_OPTIONS}", "drive push failed: private preset folders")
    if remote_links:
        _create_drive_shortcuts(project.out_official, private_dest, private_dir, "drive push failed: private out make GDrive shortcuts")

    logger.success("finished uploading to gdrive")


def dbs_sync() -> None:
    chdir_to_project()
    format_logger(log_file=LOG_DIR / "sync.log")
    project = get_project()
    FROM_DB = False
    db = load_db(FROM_DB)
    dates = load_dates(FROM_DB)

    db.write_csv(project.songs_csv)
    dates.write_csv(project.dates_csv)

    db.write_database("Songs", f"sqlite:///{project.songs_db}", if_table_exists="replace")
    dates.write_database("Dates", f"sqlite:///{project.songs_db}", if_table_exists="replace")
    logger.success(f"Synced versions of the databases, taking {'DB' if FROM_DB else 'CSV'} as source")
