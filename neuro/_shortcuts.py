import os
from pathlib import Path

from loguru import logger

from neuro import DATES_CSV, LOG_DIR, SONGS_CSV, SONGS_DB
from neuro import OFFICIAL_RELEASE_DIR, UNOFFICIALV3_DIR, COPYRIGHT_ISSUES_DIR, SETLISTS_DIR, DATA_DIR, CUSTOM_DIR, IMAGES_ROOT_DIR, OUT_UNOFFICIAL_DIR, OUT_OFFICIAL_DIR
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
remote_links = False
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

def setlists_pull() -> None:
    setlist_pull_command = f"{DRIVE_RCLONE_COMMAND} {PUBLIC_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{SETLISTS_DIR} {SETLISTS_DIR}"
    logger.info(setlist_pull_command)
    os.system(setlist_pull_command)


def setlists_push() -> None:
    setlist_push_command = f"{DRIVE_RCLONE_COMMAND} {SETLISTS_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{SETLISTS_DIR}"
    logger.info(setlist_push_command)
    os.system(setlist_push_command)


def drive_pull() -> None:
    drive_pull_command = f"{DRIVE_RCLONE_COMMAND} {UNOFFICIAL_V3_DRIVE_NAME}: temp/{UNOFFICIALV3_DIR.name}"
    logger.info(drive_pull_command)
    if os.system(drive_pull_command):
        exit(1)

# TODO command to apply my changes to unofficial archive



def drive_push() -> None:

    # public input files
    setlists_push()

    drive_push_data_command = f"{DRIVE_RCLONE_COMMAND} {DATA_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{DATA_DIR}"
    logger.info(drive_push_data_command)
    if os.system(drive_push_data_command):
        exit(1)

    drive_push_images_command = f"{DRIVE_RCLONE_COMMAND} {IMAGES_ROOT_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{IMAGES_ROOT_DIR}"
    logger.info(drive_push_images_command)
    if os.system(drive_push_images_command):
        exit(1)

    drive_push_custom_command = f"{DRIVE_RCLONE_COMMAND} {CUSTOM_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{CUSTOM_DIR}"
    logger.info(drive_push_custom_command)
    if os.system(drive_push_custom_command):
        exit(1)

    drive_push_unoffv3_in_command = f"{DRIVE_RCLONE_COMMAND} {UNOFFICIALV3_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{UNOFFICIALV3_DIR}"
    logger.info(drive_push_unoffv3_in_command)
    if os.system(drive_push_unoffv3_in_command):
        exit(1)

    # private input files
    drive_push_official_in_command = f"{DRIVE_RCLONE_COMMAND} {OFFICIAL_RELEASE_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{OFFICIAL_RELEASE_DIR}"
    logger.info(drive_push_official_in_command)
    if os.system(drive_push_official_in_command):
        exit(1)

    drive_push_copyright_issue_command = f"{DRIVE_RCLONE_COMMAND} {COPYRIGHT_ISSUES_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{COPYRIGHT_ISSUES_DIR}"
    logger.info(drive_push_copyright_issue_command)
    if os.system(drive_push_copyright_issue_command):
        exit(1)

    RCLONE_BACKEND_COMMAND = f"rclone backend shortcut{V}{DR}"

    # public out files
    drive_push_public_out_command = f"{DRIVE_RCLONE_COMMAND} {OUT_UNOFFICIAL_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_OUT_PREFIX}{LINK_OPTIONS}"
    logger.info(drive_push_public_out_command)
    if os.system(drive_push_public_out_command):
        exit(1)
    if remote_links:
        for file in [f for f in OUT_UNOFFICIAL_DIR.resolve().rglob("*.mp3") if f.is_symlink()]:
            source_drive_path = file.resolve().relative_to(OUT_UNOFFICIAL_DIR.resolve())
            shortcut_drive_path = file.relative_to(OUT_UNOFFICIAL_DIR.resolve())
            public_gdrive_link_command = f"{RCLONE_BACKEND_COMMAND} {PUBLIC_DEST}{PUBLIC_DIR} \"{REMOTE_OUT_PREFIX / source_drive_path}\" \"{REMOTE_OUT_PREFIX / shortcut_drive_path}\""
            logger.info(public_gdrive_link_command)
            os.system(public_gdrive_link_command)

    # private out files
    drive_push_private_out_command = f"{DRIVE_RCLONE_COMMAND} {OUT_OFFICIAL_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_OUT_PREFIX}{LINK_OPTIONS}"
    logger.info(drive_push_private_out_command)
    if os.system(drive_push_private_out_command):
        exit(1)
    if remote_links:
        for file in [f for f in OUT_OFFICIAL_DIR.resolve().rglob("*.mp3") if f.is_symlink()]:
            source_drive_path = file.resolve().relative_to(OUT_OFFICIAL_DIR.resolve())
            shortcut_drive_path = file.relative_to(OUT_OFFICIAL_DIR.resolve())
            private_gdrive_link_command = f"{RCLONE_BACKEND_COMMAND} {PRIVATE_DEST}{PRIVATE_DIR} \"{REMOTE_OUT_PREFIX / source_drive_path}\" \"{REMOTE_OUT_PREFIX / shortcut_drive_path}\""
            logger.info(private_gdrive_link_command)
            os.system(private_gdrive_link_command)

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
