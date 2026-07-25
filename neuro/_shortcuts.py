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
COMMON_OPTIONS = " --stats-file-name-length 0 --progress --transfers 2 --track-renames"
DRIVE_OPTIONS = " --drive-use-trash=false"
CHECK_OPTIONS = " --dry-run"
PURGE_OPTIONS = " --max-transfer=1B"

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
    os.system(f"{DRIVE_RCLONE_COMMAND} {PUBLIC_DRIVE_NAME}:{REMOTE_INPUT_PREFIX}/{SETLISTS_DIR} {SETLISTS_DIR}")


def setlists_push() -> None:
    os.system(f"{DRIVE_RCLONE_COMMAND} {SETLISTS_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{SETLISTS_DIR}")


def drive_pull() -> None:
    print(f"{DRIVE_RCLONE_COMMAND} {UNOFFICIAL_V3_DRIVE_NAME}: temp/{UNOFFICIALV3_DIR.name}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {UNOFFICIAL_V3_DRIVE_NAME}: temp/{UNOFFICIALV3_DIR.name}"):
        exit(1)

# TODO command to apply my changes to unofficial archive



def drive_push() -> None:
    setlists_push()

    print(f"{DRIVE_RCLONE_COMMAND} {DATA_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{DATA_DIR}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {DATA_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{DATA_DIR}"):
        exit(1)

    print(f"{DRIVE_RCLONE_COMMAND} {IMAGES_ROOT_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{IMAGES_ROOT_DIR}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {IMAGES_ROOT_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{IMAGES_ROOT_DIR}"):
        exit(1)

    print(f"{DRIVE_RCLONE_COMMAND} {CUSTOM_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{CUSTOM_DIR}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {CUSTOM_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{CUSTOM_DIR}"):
        exit(1)

    print(f"{DRIVE_RCLONE_COMMAND} {UNOFFICIALV3_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{UNOFFICIALV3_DIR}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {UNOFFICIALV3_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_INPUT_PREFIX}/{UNOFFICIALV3_DIR}"):
        exit(1)

    print(f"{DRIVE_RCLONE_COMMAND} {OUT_UNOFFICIAL_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_OUT_PREFIX}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {OUT_UNOFFICIAL_DIR} {PUBLIC_DEST}{PUBLIC_DIR}{REMOTE_OUT_PREFIX}"):
        exit(1)

    print(f"{DRIVE_RCLONE_COMMAND} {OFFICIAL_RELEASE_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{OFFICIAL_RELEASE_DIR}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {OFFICIAL_RELEASE_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{OFFICIAL_RELEASE_DIR}"):
        exit(1)

    print(f"{DRIVE_RCLONE_COMMAND} {COPYRIGHT_ISSUES_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{COPYRIGHT_ISSUES_DIR}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {COPYRIGHT_ISSUES_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}/{COPYRIGHT_ISSUES_DIR}"):
        exit(1)

    print(f"{DRIVE_RCLONE_COMMAND} {OUT_OFFICIAL_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}")
    if os.system(f"{DRIVE_RCLONE_COMMAND} {OUT_OFFICIAL_DIR} {PRIVATE_DEST}{PRIVATE_DIR}{REMOTE_INPUT_PREFIX}"):
        exit(1)



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
