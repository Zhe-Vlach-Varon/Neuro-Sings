"""Utils functions dedicated to interacting with the polars library."""

from collections.abc import Callable
from functools import reduce
from pathlib import Path

import polars as pl

from . import get_project
from .artists import Project
from .utils import MP3GainMode, MP3ModeTuple

# --- result caching ---
_cache: dict[str, tuple[float, pl.DataFrame]] = {}


def _get_or_load(key: str, filepath: Path, loader: Callable[[], pl.DataFrame]) -> pl.DataFrame:
    """Return a cached DataFrame if the underlying file is unchanged, otherwise reload it.

    Args:
        key (str): Unique cache key (e.g. "songs:db" or "dates:csv").
        filepath (Path): File whose mtime is used for invalidation.
        loader (Callable[[], pl.DataFrame]): Function to (re)load the DataFrame.

    Returns:
        pl.DataFrame: Cached or freshly loaded DataFrame.
    """
    mtime = filepath.stat().st_mtime
    if key in _cache:
        cached_mtime, df = _cache[key]
        if cached_mtime == mtime:
            return df
    df = loader()
    _cache[key] = (mtime, df)
    return df


def clear_cache() -> None:
    """Invalidate all cached DataFrames."""
    _cache.clear()
# --- end result caching ---

songs_schema = {
    'id': pl.Int64,
    'Title': pl.String,
    'TitleOG': pl.String,
    'Identify': pl.String,
    'Artist': pl.String,
    'ArtistOG': pl.String,
    'Cover Artist': pl.String,
    'Lead Singer': pl.String,
    'Date': pl.String,
    'Album': pl.String,
    'Album_ID': pl.Int64,
    'Image': pl.String,
    'File_IN': pl.String,
    'Hash_IN': pl.String,
    'Flags': pl.String,
    'Key': pl.String,
    'Tempo (1/4 beat)': pl.String,
    'Version': pl.String,
    'Special': pl.String,
    'Comment': pl.String,
    }

dates_schema = {
    'Date': pl.String,
    'Singer': pl.String,
    'Duet Format': pl.String
    }

def flag_expr(flag: str) -> pl.Expr:
    """Small helper function to avoid heavy expressions.

    Args:
        flag (str): Which flag to consider.

    Returns:
        pl.Expr: An expression representing the rows that have the given flag in the "Flags" column.
            Uses exact match: the Flags string is split on ";" and the flag must equal one element.
    """
    return pl.col("Flags").str.split(";").list.contains(flag)


def stack_or(flag_list: list[str]) -> pl.Expr:
    """Applies a reduction on conditions. It's literally `any(exprs)`. But the `any` function in \
        polars gives me the felling that it's not doing that.

    Args:
        flag_list (list[str]): list of flags as strings.

    Returns:
        pl.Expr: polars expression true if any of the flags is true.
    """
    return reduce(
        lambda acc, val: acc | flag_expr(val),
        flag_list,
        pl.lit(False),
    )

def stack_and(flag_list: list[str]) ->pl.Expr:
    """matches any songs with all listed flags"""
    return reduce(
        lambda acc, val: acc & flag_expr(val),
        flag_list,
        pl.lit(True),
    )
    """start with True and AND with truth of each flag being present"""


def load_db(as_db: bool = True, project: Project | None = None) -> pl.DataFrame:
    """Wrapper to loader the songs DB regardless of the backend format.

    Args:
        as_db (bool, optional): If True, will look for a `.db` database, otherwise \
            looks for a CSV file. Defaults to True.
        project (Project | None, optional): The project to load from. Defaults to the \
            active project (obtained via `get_project()`).

    Returns:
        pl.DataFrame: A polars DataFrame, regardless of the storage format.
    """
    proj = project if project is not None else get_project()
    filepath = proj.songs_db if as_db else proj.songs_csv
    key = f"songs:{proj.name}:{'db' if as_db else 'csv'}"
    return _get_or_load(key, filepath, lambda: (
        pl.read_database_uri("SELECT * FROM Songs", f"sqlite://{proj.songs_db}") if as_db
        else pl.read_csv(proj.songs_csv, schema=songs_schema)
    ))


def load_dates(as_db: bool = True, project: Project | None = None) -> pl.DataFrame:
    """Same as `load_db`. Loads dates database regardless of format.

    Args:
        as_db (bool, optional): Loads from a `.db` file or not. Defaults to True.
        project (Project | None, optional): The project to load from. Defaults to the \
            active project (obtained via `get_project()`).

    Returns:
        pl.DataFrame: Polars DataFrame with dates.
    """
    proj = project if project is not None else get_project()
    filepath = proj.songs_db if as_db else proj.dates_csv
    key = f"dates:{proj.name}:{'db' if as_db else 'csv'}"
    return _get_or_load(key, filepath, lambda: (
        pl.read_database_uri("SELECT * FROM Dates", f"sqlite://{proj.songs_db}") if as_db
        else pl.read_csv(proj.dates_csv)
    ))


PresetDict = dict[str, bool | str | list[str]]  # may also contain "group" (str) for grouping


class Preset:
    """Object to represent a preset in the TOML config file"""

    def get_list_assert(self, key: str) -> list[str]:
        """Returns include/exclude lists with type guaranteed.

        Args:
            key (str): config key, include/exclude-flags.

        Returns:
            list[str]: List of flags (may be empty).
        """
        if key in self.dict:
            ret = self.dict[key]
            assert type(ret) is list
            return ret
        else:
            return []

    def __init__(self, preset_dict: PresetDict, mp3gain_config: MP3ModeTuple, root: Path | None = None) -> None:
        """Preset constructor.

        Args:
            preset_dict (PresetDict): Dict from the TOML loading.
            mp3gain_config (MP3ModeTuple): Configuration of mp3gain.
            root (Path | None, optional): Root path from outside of the Preset part, if None\
                then the path in preset is the full path, otherwise they use the root path\
                as a common folder for all presets. Defaults to None.
        """
        self.name = preset_dict["name"]
        self.group = preset_dict.get("group", "default")
        self.dict = preset_dict
        self.include = self.get_list_assert("include-flags")
        self.exclude = self.get_list_assert("exclude-flags")

        self.mp3gain = MP3GainMode.OFF
        match mp3gain_config[0]:
            case MP3GainMode.ON_ALL:
                self.mp3gain = mp3gain_config[1]
            case MP3GainMode.PER_PRESET:
                if preset_dict.get("mp3gain", False) is True:
                    self.mp3gain = mp3gain_config[1]

        self.include_type = preset_dict.get("include-type", "or")
        self.exclude_type = preset_dict.get("exclude-type", "or")


        path = preset_dict["path"]
        assert type(path) is str

        # The preset's group (when explicitly set) is the parent directory of its
        # output, so the final path is "<group>/<path>". Presets without a group
        # (implicit "default") keep their path as-is, unchanged.
        explicit_group = preset_dict.get("group")
        if explicit_group:
            path = f"{explicit_group}/{path}"

        self.root = root
        self.subdir = path

        if root is None:
            self.path = Path(path)
        else:
            self.path = root / path


    def get_filtered_df(self, songs_df: pl.DataFrame | None = None) -> pl.DataFrame:
        """Applies filters defined in a preset to get a filtered version of the database.

        Args:
            songs_df (pl.DataFrame | None): Pre-loaded songs DataFrame to filter.
                If None, loads from disk via `load_db()`.

        Returns:
            pl.DataFrame: Filtered DB that only has rows that check the conditions.
        """
        if songs_df is None:
            songs_df = load_db()

        assert (self.include_type == "and") | (self.include_type == "or")

        if self.include_type == "and":
            includes = stack_and(self.include)  # include#1 & include#2 ...
        elif self.include_type == "or":
            includes = stack_or(self.include)  # include#1 | include#2 ...
            
        assert (self.exclude_type == "and") | (self.exclude_type == "or")

        if not self.exclude:
            # Empty exclusion list means no exclusion. Without this guard, exclude-type="and"
            # would reduce to lit(True) and .not_() would filter out every single song.
            excludes = pl.lit(False)
        elif self.exclude_type == "and":
            excludes = stack_and(self.exclude)  # exclude#1 & exclude#2 ...
        else:
            excludes = stack_or(self.exclude)  # exclude#1 | exclude#2 ...

        # Has one of the include flags and none of the exclude
        return songs_df.filter(includes & excludes.not_())
