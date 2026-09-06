"""Neuro-sings python package.

This file contains the main paths definitions."""

from pathlib import Path

ROOT_DIR = Path(".")

# ── Deprecated path constants ─────────────────────────────────────────────────
# These are kept for backward compatibility. New code should use
# `neuro.get_project()` to obtain the active project and read paths from it.
# They will be removed in a future major version.
# ──────────────────────────────────────────────────────────────────────────────

DATA_DIR = ROOT_DIR / Path("data")

SONGS_JSON = DATA_DIR / "songs_new.json"
SONGS_CSV = DATA_DIR / "songs.csv"
SONGS_DB = DATA_DIR / "songs.db"

DATES_CSV = DATA_DIR / "dates.csv"
DATES_OLD_CSV = DATA_DIR / "dates_v12.csv"

IMAGES_ROOT_DIR = ROOT_DIR / Path("images")
IMAGES_BG_DIR = IMAGES_ROOT_DIR / "bg"
IMAGES_COVERS_DIR = IMAGES_ROOT_DIR / "cover"
IMAGES_CUSTOM_DIR = IMAGES_ROOT_DIR / "custom"

SONG_ROOT_DIR = ROOT_DIR / Path("songs")
DRIVE_DIR = SONG_ROOT_DIR / "drive"
CUSTOM_DIR = SONG_ROOT_DIR / "custom"

UNOFFICIALV3_DIR = SONG_ROOT_DIR / "unofficialV3"
UNOFFV3_EXTRA = "Extra Content"
UNOFFV3_DISC66 = "DISC 66 - ARG"

OFFICIAL_RELEASE_DIR = SONG_ROOT_DIR / "officially_released_songs"
COPYRIGHT_ISSUES_DIR = SONG_ROOT_DIR / "copyright_issues"

OFFICIAL_CSV = DATA_DIR / 'official_covers.csv'
ORIGINAL_CSV = DATA_DIR / 'original_songs.csv'

SETLISTS_DIR = ROOT_DIR / "setlists"

LOG_DIR = ROOT_DIR / Path("logs")

COPYRIGHT_ISSUES_CSV = DATA_DIR / "copyright_issues.csv"

OUT_ROOT_DIR = Path("out")
OUT_UNOFFICIAL_DIR = OUT_ROOT_DIR / "unofficial_releases"
OUT_OFFICIAL_DIR = OUT_ROOT_DIR / "official_releases"

FONTS_DIR = Path("fonts")
FONT_PATH = FONTS_DIR / "First Coffee.ttf"

# ── Project abstraction (multi-project cover-artist support) ─────────────
# Re-exported so callers can `from neuro import Project, get_project`. These are
# imported *after* the path constants above so the backward-compat path in
# `neuro.config` can read them once the package has finished loading.
from neuro.artists import CoverArtist as CoverArtist
from neuro.artists import Project as Project
from neuro.config import load_project as load_project

_project: Project | None = None


def get_project() -> Project:
    """Return the active :class:`Project`, loading and caching it on first use.

    The project is read from ``config.toml`` in the current working directory (see
    :func:`neuro.config.load_project`), so selecting a project is simply a matter of
    ``cd``-ing into that project's directory.
    """
    global _project
    if _project is None:
        _project = load_project()
    return _project