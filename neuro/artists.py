"""Data model for multi-project cover-artist support.

This module defines the two value objects that encapsulate *who sings* and *where
everything lives* for a single "cover artist project" (e.g. the Neuro Twins). Downstream
code is meant to read identity/paths from a :class:`Project` instead of hardcoded
"Neuro"/"Evil" strings and module-level path constants.

The model is deliberately framework-agnostic: it only depends on the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CoverArtist:
    """One cover singer within a project.

    Attributes:
        name: The singer's canonical name as it appears in the DB "Cover Artist"/"Lead Singer"
            columns (e.g. ``"Neuro"``, ``"Evil"``).
        flag: The DB flag token for this singer (e.g. ``"neuro"``, ``"evil"``).
        display_name: The human-readable name used in ID3 tags (e.g. ``"Neuro-Sama"``).
        cover_suffix: The token used in cover-image filenames (e.g. ``"neuro"``).
        album_artist: The TPE2/TSO2 album-artist value written to tags
            (e.g. ``"Neuro-Sama/Evil Neuro"``).
    """

    name: str
    flag: str
    display_name: str
    cover_suffix: str
    album_artist: str


@dataclass
class Project:
    """A complete project: one or more cover artists sharing a DB, inputs, and outputs.

    Identity fields describe *who sings*; the path fields describe *where things are*
    (resolved relative to the current working directory at load time); the drive fields
    hold the rclone remote names used by the sync shortcuts.
    """

    name: str
    display_name: str
    artists: tuple[CoverArtist, ...]
    voice_versions: tuple[str, ...]
    duet_group_name: str

    # --- paths (all resolved relative to CWD at load time) ---
    data_dir: Path
    songs_csv: Path
    songs_db: Path
    songs_json: Path
    dates_csv: Path
    song_root: Path
    setlists_dir: Path
    images_covers_dir: Path
    images_custom_dir: Path
    images_bg_dir: Path
    out_root: Path
    out_unofficial: Path
    out_official: Path
    fonts_dir: Path

    # --- drive (rclone remote names) ---
    drive_public: str | None
    drive_private: str | None
    drive_source: str | None

    # --- helpers ---
    def singer_names(self) -> tuple[str, ...]:
        """The canonical singer names in project order (e.g. ``("Neuro", "Evil")``)."""
        return tuple(a.name for a in self.artists)

    def duet_cover_artist(self) -> str:
        """The 'Cover Artist' string for a duet between all artists (e.g. ``"Neuro & Evil"``)."""
        return " & ".join(a.name for a in self.artists)

    def flag_for(self, singer_name: str) -> str:
        """Return the flag token for a singer name.

        Raises:
            KeyError: If ``singer_name`` is not one of the project's artists.
        """
        for a in self.artists:
            if a.name == singer_name:
                return a.flag
        raise KeyError(singer_name)

    def singer_for_flag(self, flag: str) -> CoverArtist:
        """Return the :class:`CoverArtist` whose flag token matches ``flag``.

        Raises:
            KeyError: If ``flag`` is not one of the project's artists.
        """
        for a in self.artists:
            if a.flag == flag:
                return a
        raise KeyError(flag)

    def all_singer_flags(self) -> tuple[str, ...]:
        """All singer flag tokens, each with a trailing ``;`` (e.g. ``("neuro;", "evil;")``).

        Convenient for the flag-string ``str.replace`` operations in the flag pipeline.
        """
        return tuple(a.flag + ";" for a in self.artists)
