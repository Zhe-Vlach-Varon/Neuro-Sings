"""Neuro-sings python package.

This file contains the main paths definitions."""

from pathlib import Path

ROOT_DIR = Path(".")

DATA_DIR = ROOT_DIR / Path("data")

SONGS_JSON = DATA_DIR / "songs_new.json"
SONGS_CSV = DATA_DIR / "songs.csv"
SONGS_DB = DATA_DIR / "songs.db"

DATES_CSV = DATA_DIR / "dates.csv"
DATES_OLD_CSV = DATA_DIR / "dates_v12.csv"

IMAGES_ROOT_DIR = ROOT_DIR / Path("images")
IMAGES_BG_DIR = IMAGES_ROOT_DIR / "bg"
IMAGES_DATES_DIR = IMAGES_ROOT_DIR / "dates"
IMAGES_COVERS_DIR = IMAGES_ROOT_DIR / "cover"
IMAGES_CUSTOM_DIR = IMAGES_ROOT_DIR / "custom"

SONG_ROOT_DIR = ROOT_DIR / Path("songs")
DRIVE_DIR = SONG_ROOT_DIR / "drive"
CUSTOM_DIR = SONG_ROOT_DIR / "custom"

UNOFFICIALV3_DIR = SONG_ROOT_DIR / "unofficialV3"
UNOFFV3_DISC1 = "DISC 1 - Humble Beginnings (2023-01-03 - 2023-05-17)"
UNOFFV3_DISC2 = "DISC 2 - A Small Upgrade (2023-05-27 - 2023-06-08)"
UNOFFV3_DISC3 = "DISC 3 - The Gold Standard (2023-06-21 - 2023-12-06)"
UNOFFV3_DISC4 = "DISC 4 - First Anniversary (2023-12-19 - 2024-06-26)"
UNOFFV3_DISC5 = "DISC 5 - Non-Stop Innovation (2024-07-10 - 2024-11-17)"
UNOFFV3_DISC6 = "DISC 6 - Second Anniversary (2024-11-17 - 2025-05-15)"
UNOFFV3_DISC7 = "DISC 7 - Background Running Process (2025-05-28 - 2025-11-26)"
UNOFFV3_DISC8 = "DISC 8 - Third Anniversary (2025-12-19 - Present)"
UNOFFV3_DISC66 = "EXTRA CONTENT/DISC 66 - ARG"

LOG_DIR = ROOT_DIR / Path("logs")
