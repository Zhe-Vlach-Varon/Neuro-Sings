import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loguru import logger

from neuro import DATES_CSV, LOG_DIR, SONGS_CSV, SONGS_DB
from neuro import OFFICIAL_RELEASE_DIR, UNOFFICIALV3_DIR, COPYRIGHT_ISSUES_DIR, SETLISTS_DIR, DATA_DIR, CUSTOM_DIR, IMAGES_ROOT_DIR, OUT_UNOFFICIAL_DIR, OUT_OFFICIAL_DIR, FONTS_DIR
from neuro.polars_utils import load_dates, load_db
from neuro.utils import format_logger

# pb's original drive, no longer updated
ORIGINAL_AUDIO_DRIVE_NAME = "Neuro-sama-audio"

# original maintainer's Neuro-Sings drive
ORIGINAL_NEURO_SINGS_DRIVE_NAME = "Neuro-Sings"

# Current Source Drive
UNOFFICIAL_V3_DRIVE_NAME = "unofficialV3"

# Zhe_Vlach_Varon's current drives
PUBLIC_DRIVE_NAME = "Neuro-Sings-ZVV"
PRIVATE_DRIVE_NAME = "Neuro-Sings-ZVV-official-releases"

# Path constants for local and remote Paths
REMOTE_INPUT_PREFIX = Path("_inputs")
REMOTE_OUT_PREFIX = Path("out")

DOT_VSCODE_DIR = Path(".vscode")

# input files for upload to public folder
# DATA_DIR
# IMAGES_ROOT_DIR
# SETLISTS_DIR
# CUSTOM_DIR
# UNOFFICIALV3_DIR

# input files for upload to private folder
# COPYRIGHT_ISSUES_DIR
# OFFICIAL_RELEASE_DIR

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

verb = True
V = " -v" if verb else ""

dryrun = False
DR = CHECK_OPTIONS if dryrun else ""

# test run, copy to local folder instead of drive
TR = False

# rclone complete commands
DRIVE_RCLONE_COMMAND = f"{RCLONE_SYNC}{COMMON_OPTIONS}{DRIVE_OPTIONS}{V}{DR}"

LOCAL_TEST_DIR = Path("temp")
LOCAL_PUBLIC_DIR = Path(PUBLIC_DRIVE_NAME)
LOCAL_PRIVATE_DIR = Path(PRIVATE_DRIVE_NAME)

PUBLIC_DEST = f"{PUBLIC_DRIVE_NAME}:" if not TR else f"{LOCAL_TEST_DIR}/"
PRIVATE_DEST = f"{PRIVATE_DRIVE_NAME}:" if not TR else f"{LOCAL_TEST_DIR}/"

PUBLIC_DIR = f"{LOCAL_PUBLIC_DIR}/" if TR else ""
PRIVATE_DIR = f"{LOCAL_PRIVATE_DIR}/" if TR else ""

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


def _create_drive_shortcuts(out_dir: Path, dest: str, dir_prefix: str, error_label: str, max_workers: int = SHORTCUT_MAX_WORKERS) -> None:
    """Create GDrive shortcuts for all symlinked .mp3 files under out_dir.

    The calls are independent → run through a small thread pool instead of sequentially
    (thousands of symlinks would otherwise mean thousands of serial round-trips).
    Fails fast like before: the first rclone error cancels the pending ones and exits 1.

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
    commands: list[tuple[Path, str]] = []
    for file in [f for f in base.rglob("*.mp3") if f.is_symlink()]:
        source_drive_path = file.resolve().relative_to(base)
        shortcut_drive_path = file.relative_to(base)
        cmd = (
            f"{RCLONE_BACKEND_COMMAND} {dest}{dir_prefix}"
            f" \"{REMOTE_OUT_PREFIX / source_drive_path}\""
            f" \"{REMOTE_OUT_PREFIX / shortcut_drive_path}\""
        )
        commands.append((file, cmd))

    if not commands:
        return

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
    setlist_pull_command = f"{DRIVE_RCLONE_COMMAND} {PUBLIC_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{SETLISTS_DIR} {SETLISTS_DIR}"
    _rclone(setlist_pull_command, "setlists pull failed")


def setlists_push() -> None:
    setlist_push_command = f"{DRIVE_RCLONE_COMMAND} {SETLISTS_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{SETLISTS_DIR}"
    _rclone(setlist_push_command, "setlists push failed")


def drive_pull() -> None:
    drive_pull_command = f"{DRIVE_RCLONE_COMMAND} {UNOFFICIAL_V3_DRIVE_NAME}: temp/{UNOFFICIALV3_DIR.name}"
    _rclone(drive_pull_command, "drive pull failed")

# TODO command to apply my changes to unofficial archive metadata

def inputs_pull() -> None:
    # public input files
    setlists_pull()

    _rclone(f"{DRIVE_RCLONE_COMMAND} {PUBLIC_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{DATA_DIR} {DATA_DIR}", "drive pull failed: data")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {PUBLIC_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{IMAGES_ROOT_DIR} {IMAGES_ROOT_DIR}", "drive pull failed: images")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {PUBLIC_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{CUSTOM_DIR} {CUSTOM_DIR}", "drive pull failed: custom")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {PUBLIC_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{UNOFFICIALV3_DIR} {UNOFFICIALV3_DIR}", "drive pull failed: unofficialV3")

    # private input files
    _rclone(f"{DRIVE_RCLONE_COMMAND} {PRIVATE_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{OFFICIAL_RELEASE_DIR} {OFFICIAL_RELEASE_DIR}", "drive pull failed: official releases")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {PRIVATE_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{COPYRIGHT_ISSUES_DIR} {COPYRIGHT_ISSUES_DIR}", "drive pull failed: copyright issues")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {PRIVATE_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{FONTS_DIR} {FONTS_DIR}", "drive pull failed: fonts")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {PRIVATE_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{DOT_VSCODE_DIR} {DOT_VSCODE_DIR}", "drive pull failed: .vscode")

    logger.success("finished downloading input files from gdrive")


def drive_push() -> None:

    # public input files
    setlists_push()

    _rclone(f"{DRIVE_RCLONE_COMMAND} {DATA_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{DATA_DIR}", "drive push failed: data")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {IMAGES_ROOT_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{IMAGES_ROOT_DIR}", "drive push failed: images")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {CUSTOM_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{CUSTOM_DIR}", "drive push failed: custom")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {UNOFFICIALV3_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{UNOFFICIALV3_DIR}", "drive push failed: unofficialV3")

    # private input files
    _rclone(f"{DRIVE_RCLONE_COMMAND} {OFFICIAL_RELEASE_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{OFFICIAL_RELEASE_DIR}", "drive push failed: official releases")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {COPYRIGHT_ISSUES_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{COPYRIGHT_ISSUES_DIR}", "drive push failed: copyright issues")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {FONTS_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{FONTS_DIR}", "drive push failed: fonts")
    _rclone(f"{DRIVE_RCLONE_COMMAND} {DOT_VSCODE_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{DOT_VSCODE_DIR}", "drive push failed: .vscode")

    # public out files
    _rclone(f"{DRIVE_RCLONE_COMMAND} {OUT_UNOFFICIAL_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_OUT_PREFIX}{LINK_OPTIONS}", "drive push failed: public out files")
    if remote_links:
        _create_drive_shortcuts(OUT_UNOFFICIAL_DIR, PUBLIC_DEST, PUBLIC_DIR, "drive push failed: public out make GDrive shortcuts")

    # private out files
    _rclone(f"{DRIVE_RCLONE_COMMAND} {OUT_OFFICIAL_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_OUT_PREFIX}{LINK_OPTIONS}", "drive push failed: private out files")
    if remote_links:
        _create_drive_shortcuts(OUT_OFFICIAL_DIR, PRIVATE_DEST, PRIVATE_DIR, "drive push failed: private out make GDrive shortcuts")

    logger.success("finished uploading to gdrive")


def dbs_sync() -> None:
    format_logger(log_file=LOG_DIR / "sync.log")
    FROM_DB = False
    db = load_db(FROM_DB)
    dates = load_dates(FROM_DB)

    db.write_csv(SONGS_CSV)
    dates.write_csv(DATES_CSV)

    db.write_database("Songs", f"sqlite:///{SONGS_DB}", if_table_exists="replace")
    dates.write_database("Dates", f"sqlite:///{SONGS_DB}", if_table_exists="replace")
    logger.success(f"Synced versions of the databases, taking {'DB' if FROM_DB else 'CSV'} as source")
