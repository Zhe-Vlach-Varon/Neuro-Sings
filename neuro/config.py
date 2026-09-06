"""Load the active :class:`~neuro.artists.Project` from ``config.toml``.

``load_project`` parses ``config.toml`` and returns a :class:`Project`. If the config has
no ``[project]`` section (i.e. a pre-refactor config), it synthesizes a ``Project`` from
the legacy module-level constants in :mod:`neuro` so existing setups keep working
unchanged.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from neuro.artists import CoverArtist, Project


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


def _synthesized_project() -> Project:
    """Build a :class:`Project` from the legacy module-level constants (backward compat).

    ``import neuro`` is deferred to the call site (not module import time) to avoid a
    circular import: :mod:`neuro` imports this module, so we can only read its constants
    once the package has finished loading.
    """
    import neuro  # deferred on purpose — see docstring

    return Project(
        name="neuro",
        display_name="Neuro Twins",
        artists=(
            CoverArtist(
                name="Neuro",
                flag="neuro",
                display_name="Neuro-Sama",
                cover_suffix="neuro",
                album_artist="Neuro-Sama/Evil Neuro",
            ),
            CoverArtist(
                name="Evil",
                flag="evil",
                display_name="Evil Neuro",
                cover_suffix="evil",
                album_artist="Neuro-Sama/Evil Neuro",
            ),
        ),
        voice_versions=("v1", "v2", "v3"),
        duet_group_name="Twins",
        data_dir=neuro.DATA_DIR,
        songs_csv=neuro.SONGS_CSV,
        songs_db=neuro.SONGS_DB,
        songs_json=neuro.SONGS_JSON,
        dates_csv=neuro.DATES_CSV,
        song_root=neuro.SONG_ROOT_DIR,
        setlists_dir=neuro.SETLISTS_DIR,
        images_covers_dir=neuro.IMAGES_COVERS_DIR,
        images_custom_dir=neuro.IMAGES_CUSTOM_DIR,
        images_bg_dir=neuro.IMAGES_BG_DIR,
        out_root=neuro.OUT_ROOT_DIR,
        out_unofficial=neuro.OUT_UNOFFICIAL_DIR,
        out_official=neuro.OUT_OFFICIAL_DIR,
        fonts_dir=neuro.FONTS_DIR,
        drive_public="Neuro-Sings-ZVV",
        drive_private="Neuro-Sings-ZVV-official-releases",
        drive_source="unofficialV3",
    )


def load_project(config_path: Path = Path("config.toml")) -> Project:
    """Parse ``config.toml`` and return a :class:`Project` instance.

    Paths are resolved relative to the current working directory (matching the existing
    ``ROOT_DIR = Path(".")`` design), so a project is selected simply by ``cd``-ing into its
    directory. If the config lacks a ``[project]`` section, a backward-compatible project is
    synthesized from the legacy constants.

    Args:
        config_path: Path to the config file. Defaults to ``config.toml`` in the CWD.

    Returns:
        A fully populated :class:`Project`.
    """
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    if "project" not in raw:
        return _synthesized_project()

    p = raw["project"]
    out_cfg = raw.get("output", {})
    drive_cfg = raw.get("drive", {})

    artists = tuple(_artist_from_dict(a) for a in p.get("artists", ()))
    base = Path(".")
    out_root = Path(out_cfg.get("out-root", "out"))

    return Project(
        name=p["name"],
        display_name=p.get("display-name", p["name"]),
        artists=artists,
        voice_versions=tuple(p.get("voice-versions", ("v1", "v2", "v3"))),
        duet_group_name=p.get("duet-group-name", "Twins"),
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
        drive_public=drive_cfg.get("public"),
        drive_private=drive_cfg.get("private"),
        drive_source=drive_cfg.get("source"),
    )
