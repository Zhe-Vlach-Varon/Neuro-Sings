import os
import shlex
import subprocess
import tomllib as toml
from pathlib import Path
from time import time

import polars as pl
from loguru import logger

from neuro import DRIVE_DIR, UNOFFICIALV3_DIR, LOG_DIR, SONG_ROOT_DIR, UNOFFV3_EXTRA, UNOFFV3_DISC66, COPYRIGHT_ISSUES_DIR
from neuro.checks import check_are_dbs_identical, check_all_group_coverage, check_group_coverage
from neuro.detection import export_json, extract_all
from neuro.file_tags import CustomSong, DriveSong, Song
from neuro.polars_utils import Preset, load_dates, load_db
from neuro.utils import MP3GainMode, MP3ModeTuple, format_logger, time_format, get_audio_hash_to_file_mapping

DateDict = dict[str, dict[str, str]]

g_hash_to_file_dict: dict[str, str] = {}


def new_batch_detection() -> None:
    """Re-runs the song detection based on regex. Adds songs that aren't already in\
        the database in a JSON file for them to be reviewed.
    """
    format_logger(log_file=LOG_DIR / "batches.log")
    # These 3 lines could be one call, but it would just make the code less clear
    out = extract_all()  # Extracts data
    export_json(out)  # Writing into JSON


def load_config() -> tuple[dict, Path | None]:
    """Loads the config.toml file and extracts the output root.

    Returns:
        tuple[dict, Path | None]: The parsed config dict and the OUT_ROOT path
            (None if use-root is disabled).
    """
    with open("config.toml", "rb") as file:
        config = toml.load(file)
    cfg_out = config["output"]
    OUT_ROOT = Path(cfg_out["out-root"]) if cfg_out["use-root"] else None
    return config, OUT_ROOT


def is_official_release(song: Song) -> bool:
    """Checks if the song should be treated as an official release.

    Args:
        song (Song): The song instance.

    Returns:
        bool: True if the song has any of originals, official, or copyright_issues flags.
    """
    return song.flags.originals or song.flags.official or song.flags.copyright_issues


def classify_song(song_dict: dict, dates_dict: DateDict) -> DriveSong | CustomSong:
    """Classifies a song as a DriveSong or CustomSong based on its File_IN path.

    Drive songs come from the drive, unofficialV3 (excluding DISC 66 ARG), or copyright issues.
    Everything else is a custom song (collabs, subathon mixes, etc.).

    Args:
        song_dict (dict): Song data from the database.
        dates_dict (DateDict): Date dictionary for DriveSong construction.

    Returns:
        DriveSong | CustomSong: The appropriate Song subclass instance.
    """
    file_in = Path(song_dict["File_IN"])
    if (
        file_in.is_relative_to(DRIVE_DIR)
        or (file_in.is_relative_to(UNOFFICIALV3_DIR) and not file_in.is_relative_to(UNOFFICIALV3_DIR / UNOFFV3_EXTRA / UNOFFV3_DISC66))
        or file_in.is_relative_to(COPYRIGHT_ISSUES_DIR)
    ):
        return DriveSong(song_dict, dates_dict.get(song_dict["Date"], {}))
    return CustomSong(song_dict)


def resolve_output_paths(song: Song, root: Path | None, subdir: str) -> dict[str, Path | None]:
    """Resolves the output file and metadata paths for a song.

    Official releases (originals/official/copyright_issues) get song files in
    'official_releases/' and metadata files in 'unofficial_releases/'.
    Non-official songs get song files in 'unofficial_releases/'.

    Args:
        song (Song): The song instance.
        root (Path | None): The output root directory, or None for relative paths.
        subdir (str): Subdirectory within the release folder (e.g. preset path or 'albums/AlbumName').

    Returns:
        dict[str, Path | None]: Dictionary with 'song_files' and 'metadata_files' paths.
    """
    base = root if root is not None else Path(".")
    if is_official_release(song):
        return {
            "song_files": base / "official_releases" / subdir,
            "metadata_files": base / "unofficial_releases" / subdir,
        }
    return {
        "song_files": base / "unofficial_releases" / subdir,
        "metadata_files": None,
    }


def generate_from_preset(preset: Preset, dates_dict: DateDict, create_placeholders: bool = False, make_links: bool = False, songs_df: pl.DataFrame | None = None) -> None:
    """Generates all songs from a preset, filters songs that respect filters.

    Args:
        preset (Preset): Preset configuration.
        dates_dict (DateDict): Date dict to pass to drive song constructor.
        create_placeholders (bool): If True, create placeholder files for official songs.
        make_links (bool): If True, create symlinks to album files instead of copying.
        songs_df (pl.DataFrame | None): Pre-loaded songs DataFrame to avoid repeated DB reads.
    """

    global g_hash_to_file_dict

    if not len(g_hash_to_file_dict):
        g_hash_to_file_dict = get_audio_hash_to_file_mapping(SONG_ROOT_DIR)

    t = time()
    songs_filtered = preset.get_filtered_df(songs_df)
    N_SONGS = len(songs_filtered)  # computed once before the loop (was re-read on every iteration)

    # os.makedirs is a syscall even with exist_ok=True, so remember dirs already created this run.
    made_dirs: set[Path] = set()
    def ensure_dir(d: Path) -> None:
        if d not in made_dirs:
            os.makedirs(d, exist_ok=True)
            made_dirs.add(d)

    for i, song_dict in enumerate(songs_filtered.iter_rows(named=True)):
        s = classify_song(song_dict, dates_dict)

        final_out_paths = resolve_output_paths(s, preset.root, preset.subdir)

        ensure_dir(final_out_paths['song_files'])
        if s.hash_in in g_hash_to_file_dict.keys():
            if make_links:
                # Use the album path that generate_albums would use as the source.
                # preset.root is None when use-root = false: fall back to CWD like resolve_output_paths() does,
                # instead of building a literal "None" directory.
                release_dir = "unofficial_releases" if not is_official_release(s) else "official_releases"
                root_base = preset.root if preset.root is not None else Path(".")
                album_song_dir = root_base / release_dir / 'albums' / s.album
                existing_path = album_song_dir / f"{s.file_name(s.flags.as_custom, numberedFiles=False)}.mp3" if isinstance(s, DriveSong) else album_song_dir / f"{s.file_name(not s.flags.as_drive, numberedFiles=False)}{s.file.suffix}"
                created = s.create_file_link(create=False, out_dir=final_out_paths['song_files'], existing_path=existing_path)
            else:
                created = s.create_out_file(create=False, out_dir=final_out_paths['song_files'])
                if created:
                    s.apply_tags(True)
            logger.debug(f"[GEN] [{preset.name}] [{i + 1:3d}/{N_SONGS}] {'Generated' if created else 'Skipped'} {song_dict['Title']}")
            if create_placeholders and is_official_release(s):
                ensure_dir(final_out_paths['metadata_files'])
                s.create_placeholder_files(out_dir=final_out_paths['metadata_files'])
        elif is_official_release(s):
            logger.warning(f"[GEN] [{preset.name}] [{i + 1:3d}/{N_SONGS}] Skipped {song_dict['Title']} official song file not found: {song_dict['File_IN']}")
            if create_placeholders:
                s.create_placeholder_files(out_dir=final_out_paths['song_files'])
                s.create_placeholder_files(out_dir=final_out_paths['metadata_files'])
            continue
        else:
            logger.error(f"[GEN] [{preset.name}] [{i + 1:3d}/{N_SONGS}] ERROR {song_dict['Title']} unofficial song file not found: {song_dict['File_IN']}")
            exit(1)
    run_mp3gain(preset)
    logger.success(f"[GEN] Done converting {N_SONGS} songs in {time_format(time() - t)} !")


def get_presets_for_group(config: dict, group: str | None = None) -> list[dict]:
    """Returns the preset dicts belonging to a group.

    Args:
        config (dict): The parsed config.toml.
        group (str | None): Group name to filter by. If None, all presets are returned.
            Presets without an explicit `group` field belong to the "default" group.

    Returns:
        list[dict]: Matching preset dicts.

    Raises:
        ValueError: If the requested group matches no preset.
    """
    presets = config["Presets"]
    if group is None:
        return presets
    if group == "default":
        matched = [p for p in presets if p.get("group", "default") == "default"]
    else:
        matched = [p for p in presets if p.get("group", "default") == group]
    if not matched:
        available = sorted({p.get("group", "default") for p in presets})
        raise ValueError(f"Group '{group}' matches no preset. Available groups: {available}")
    return matched


def generate_songs_group(group: str) -> None:
    """CLI entrypoint to generate only the presets belonging to a given group.

    Args:
        group (str): Group name to generate, or "all" for every preset,
            or "default" for presets that have no explicit group.
    """
    config = load_config()[0]
    presets = get_presets_for_group(config, None if group == "all" else group)
    _generate_presets(presets, create_placeholders=False)


def check_group() -> None:
    """CLI entrypoint to verify that a preset group partitions the database.

    Usage: ``check-group [group]`` — with no argument (or ``all``) it checks every group
    present in config.toml; otherwise it checks the named group (e.g. ``zvv_sort``).
    """
    import sys
    group = sys.argv[1] if len(sys.argv) > 1 else None
    format_logger(log_file=LOG_DIR / "checks.log")
    if group is None or group == "all":
        check_all_group_coverage()
    else:
        check_group_coverage(group)


def generate_songs(create_placeholders: bool = False) -> None:
    """Generates all songs files. For each files it first copies the files into\
    its destination, then edits the metadata of the destination file. This is\
    just to avoid tempering the original files.\
    Generates songs in preset groups.
    """
    config = load_config()[0]
    _generate_presets(get_presets_for_group(config, None), create_placeholders=create_placeholders)


def _generate_presets(presets: list[dict], create_placeholders: bool = False) -> None:
    """Shared generation loop over a list of preset dicts (all or a single group)."""
    format_logger(log_file=LOG_DIR / "generation.log")
    logger.info(f"[GEN] Starting generation batch ({len(presets)} presets)")

    # Avoids wrong generations due to inconsistent databases
    try:
        check_are_dbs_identical()
    except ValueError as e:
        logger.error("[GEN] Error while comparing Databases")
        raise e

    config, OUT_ROOT = load_config()

    make_links = config["output"]["make-links"]

    mp3gain = parse_mp3gain(config)

    # Start time
    t = time()

    # Easier data format to deal with
    dates_dict: DateDict = {k["Date"]: k for k in load_dates().iter_rows(named=True)}

    # Load the songs DB once and share it across all presets
    songs_df = load_db()

    for preset in presets:
        logger.info(f"[GEN] Generating preset '{preset['name']}'")
        preset_obj = Preset(preset, mp3gain, OUT_ROOT)
        generate_from_preset(preset_obj, dates_dict, create_placeholders, make_links, songs_df)

    logger.success(f"[GEN] Generated all presets in {time_format(time() - t)} !")


def generate_albums(create_placeholders: bool = False) -> None:
    """generates all songs sorted by album"""

    global g_hash_to_file_dict

    if not len(g_hash_to_file_dict):
        g_hash_to_file_dict = get_audio_hash_to_file_mapping(SONG_ROOT_DIR)

    format_logger(log_file=LOG_DIR / "generation.log")
    logger.info("[GEN] Starting generation batch")

    # Avoids wrong generations due to inconsistent databases
    try:
        check_are_dbs_identical()
    except ValueError as e:
        logger.error("[GEN] Error while comparing Databases")
        raise e

    config, OUT_ROOT = load_config()

    mp3gain = parse_mp3gain(config)

    # Start time
    t = time()

    songDB = load_db()

    dates_dict: DateDict = {k["Date"]: k for k in load_dates().iter_rows(named=True)}

    N_SONGS = len(songDB)  # computed once before the loop (was re-read on every iteration)

    # os.makedirs is a syscall even with exist_ok=True, so remember dirs already created this run.
    made_dirs: set[Path] = set()
    def ensure_dir(d: Path) -> None:
        if d not in made_dirs:
            os.makedirs(d, exist_ok=True)
            made_dirs.add(d)

    for i, song_dict in enumerate(songDB.iter_rows(named=True)):
        s = classify_song(song_dict, dates_dict)

        album = s.album
        final_out_paths = resolve_output_paths(s, OUT_ROOT, f"albums/{album}")

        ensure_dir(final_out_paths['song_files'])
        if s.hash_in in g_hash_to_file_dict.keys():
            created = s.create_out_file(create=False, out_dir=final_out_paths['song_files'])
            if created:
                s.apply_tags(True)
            logger.debug(f"[GEN] [{i+1:4d}/{N_SONGS}] [{album}] {'Generated' if created else 'Skipped'} {song_dict['Title']}")
            if create_placeholders and is_official_release(s):
                ensure_dir(final_out_paths['metadata_files'])
                s.create_placeholder_files(out_dir=final_out_paths['metadata_files'])
        elif is_official_release(s):
            logger.warning(f"[GEN] [{i+1:4d}/{N_SONGS}] [{album}] Skipped {song_dict['Title']} official song file not found: {song_dict['File_IN']}")
            if create_placeholders:
                s.create_placeholder_files(out_dir=final_out_paths['song_files'])
                s.create_placeholder_files(out_dir=final_out_paths['metadata_files'])
            continue
        else:
            logger.error(f"[GEN] [{i+1:4d}/{N_SONGS}] [{album}] ERROR {song_dict['Title']} unofficial song file not found: {song_dict['File_IN']}")
            exit(1)


def parse_mp3gain(config: dict) -> MP3ModeTuple:
    """Gets the mp3gain global config from the config file.

    Args:
        config (dict): Dictionnary representing the whole configuration file.

    Raises:
        ValueError: If the configuration has unexpected.

    Returns:
        MP3ModeTuple: Tuple with the mode (per-preset or on-all) and the type \
            of gain modification (tag or gain on file).
    """
    mp3gain: MP3ModeTuple
    if "mp3gain" in config["features"]["activated"]:
        mp3_config = config["features"]["mp3gain"]
        match mp3_config["mode"]:
            case "per-preset":
                mode = MP3GainMode.PER_PRESET
            case "on-all":
                mode = MP3GainMode.ON_ALL
            case x:
                logger.error(f"Unknown mp3gain mode '{x}'")
                raise ValueError(f"Unknown mp3gain mode '{x}'")
        match mp3_config["type"]:
            case "gain":
                type = MP3GainMode.GAIN
            case "tag":
                type = MP3GainMode.TAG
            case _ as x:
                logger.error(f"Unknown mp3gain type '{x}'")
                raise ValueError(f"Unknown mp3gain type '{x}'")
        mp3gain = (mode, type)
    else:
        mp3gain = (MP3GainMode.OFF, MP3GainMode.OFF)

    return mp3gain


def run_mp3gain(preset: Preset) -> None:
    """Runs gain equalization for a given preset.

    Args:
        preset (Preset): The preset to run mp3gain on, contains all relevant information.
    """
    if preset.mp3gain is MP3GainMode.OFF:
        return

    # Skip presets with an empty/missing output dir instead of letting mp3gain fail on an unexpanded glob
    mp3s = list(preset.path.glob("*.mp3"))
    if not mp3s:
        logger.debug(f"[MP3G] Skipping preset '{preset.name}': no mp3 files in {preset.path}")
        return

    logger.info(f"[GEN] Running mp3gain for preset {preset.name} ({len(mp3s)} files)")
    options = "-r -k" if preset.mp3gain is MP3GainMode.GAIN else ""
    # One log per preset, so every run's output survives instead of being truncated by the next one
    OUT_LOG = LOG_DIR / f"mpgain_{preset.name}.log"
    cmd = f"mp3gain {options} {shlex.quote(str(preset.path))}/*.mp3 > {shlex.quote(str(OUT_LOG))} 2>&1"
    # check=False on purpose: a nonzero exit is expected and reported via the log, not raised
    result = subprocess.run(cmd, shell=True, check=False)
    if result.returncode != 0:
        logger.error(f"[MP3G] mp3gain failed for preset '{preset.name}' (exit code {result.returncode}), see {OUT_LOG}")


def mp3gain_standalone() -> None:
    """Runs mp3gain on all presets without creating the files.

    Bypasses the per-preset `mp3gain` booleans: this command exists to apply the configured\
        gain type over every existing preset output, so a preset's own boolean must not disable it.
    """
    format_logger(log_file=LOG_DIR / "generation.log")
    logger.info("[MP3G] Starting mp3gain batch")

    config, OUT_ROOT = load_config()

    mp3gain = parse_mp3gain(config)
    if mp3gain[1] not in (MP3GainMode.GAIN, MP3GainMode.TAG):
        logger.error("[MP3G] No valid mp3gain type configured: add 'mp3gain' to [features].activated and set "
                     "[features.mp3gain].type to 'gain' or 'tag'")
        exit(1)

    # Force ON_ALL so the per-preset booleans (currently all false) don't disable everything
    preset_mp3gain = (MP3GainMode.ON_ALL, mp3gain[1])

    for preset in config["Presets"]:
        logger.info(f"[MP3G] Running preset '{preset['name']}'")
        preset_obj = Preset(preset, preset_mp3gain, OUT_ROOT)
        run_mp3gain(preset_obj)


if __name__ == "__main__":
    generate_songs()
