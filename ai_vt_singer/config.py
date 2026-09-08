"""Load the active :class:`~ai_vt_singer.artists.Project` from ``config.toml``.

``load_project`` parses ``config.toml`` and returns a :class:`Project`. The config **must**
contain a ``[project]`` section; a ``ValueError`` is raised otherwise.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from .artists import CoverArtist, Project


def _artist_from_dict(d: dict) -> CoverArtist:
    """Build a :class:`CoverArtist` from a ``[[project.artists]]`` TOML table.

    ``display-name`` and ``cover-suffix`` default to sensible values derived from the
    required ``name``/``flag`` keys so a minimal artist entry is still valid.
    """
    name = d["name"]
    flag = d["flag"]
    display_name = d.get("display-name", name)
    return CoverArtist(
        name=name,
        flag=flag,
        display_name=display_name,
        cover_suffix=d.get("cover-suffix", flag),
        album_artist=d.get("album-artist", display_name),
    )


def load_project(config_path: Path = Path("config.toml")) -> Project:
    """Parse ``config.toml`` and return a :class:`Project` instance.

    Paths are resolved relative to the current working directory (matching the existing
    ``ROOT_DIR = Path(".")`` design), so a project is selected simply by ``cd``-ing into its
    directory. The config **must** contain a ``[project]`` section.

    Args:
        config_path: Path to the config file. Defaults to ``config.toml`` in the CWD.

    Returns:
        A fully populated :class:`Project`.

    Raises:
        ValueError: If the config lacks a ``[project]`` section.
    """
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    if "project" not in raw:
        raise ValueError(
            f"Config file '{config_path}' must contain a [project] section. "
            f"See the multi-project support docs for the expected format."
        )

    p = raw["project"]
    out_cfg = raw.get("output", {})
    drive_cfg = raw.get("drive", {})

    artists = tuple(_artist_from_dict(a) for a in p.get("artists", ()))
    base = Path(".")
    out_root = Path(out_cfg.get("out-root", "out"))

    # Thumbnail bg image mappings
    thumbnails = p.get("thumbnails", {})
    bg_solo = thumbnails.get("solo")   # dict[str, dict[str, str]] | None
    bg_duet = thumbnails.get("duet")   # dict[str, str] | None

    # Project-specific overrides
    arg_singers = tuple(p.get("arg-singers", ()))
    arg_album_name = p.get("arg-album")  # None → extract_arg() derives "<display-name> ARG"
    arg_subdir = p.get("arg-subdir")    # None → no ARG subdirectory
    song_overrides = p.get("song-overrides", {})
    name_tag_overrides = song_overrides.get("name-tag", {})
    version_overrides = song_overrides.get("version", {})

    # Song directories (optional override; defaults cover common cases)
    default_song_dirs = {
        "drive": "drive",
        "custom": "custom",
        "unofficialv3": "unofficialV3",
        "official": "officially_released_songs",
        "copyright": "copyright_issues",
    }
    song_dirs_cfg = p.get("song-dirs", {})
    song_dirs = {**default_song_dirs, **song_dirs_cfg}

    # Duet group name: required for multi-artist projects
    duet_group_name = p.get("duet-group-name")
    if duet_group_name is None and len(artists) >= 2:
        duet_group_name = " & ".join(a.name for a in artists)
    elif duet_group_name is None:
        duet_group_name = ""

    return Project(
        name=p["name"],
        display_name=p.get("display-name", p["name"]),
        artists=artists,
        voice_versions=tuple(p.get("voice-versions", ("v1", "v2", "v3"))),
        duet_group_name=duet_group_name,
        data_dir=base / "data",
        songs_csv=base / "data" / "songs.csv",
        songs_db=base / "data" / "songs.db",
        songs_json=base / "data" / "songs_new.json",
        dates_csv=base / "data" / "dates.csv",
        song_root=base / "songs",
        setlists_dir=base / "setlists",
        images_covers_dir=base / "images" / "cover",
        images_custom_dir=base / "images" / "custom",
        images_bg_dir=base / "images" / "bg",
        out_root=out_root,
        out_unofficial=out_root / "unofficial_releases",
        out_official=out_root / "official_releases",
        fonts_dir=base / "fonts",
        logs_dir=base / "logs",
        drive_public=drive_cfg.get("public"),
        drive_private=drive_cfg.get("private"),
        drive_source=drive_cfg.get("source"),
        bg_solo_images=bg_solo,
        bg_duet_images=bg_duet,
        arg_singers=arg_singers,
        arg_album_name=arg_album_name,
        arg_subdir=arg_subdir,
        song_dirs=song_dirs,
        song_name_tag_overrides=name_tag_overrides,
        song_version_overrides=version_overrides,
    )
