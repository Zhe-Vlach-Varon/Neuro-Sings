import os
import tomllib as toml
from pathlib import Path
from time import time

from loguru import logger

from neuro import DRIVE_DIR, CUSTOM_DIR, UNOFFICIALV3_DIR, LOG_DIR, SONG_ROOT_DIR, UNOFFV3_DISC66
from neuro.checks import check_are_dbs_identical
from neuro.detection import export_json, extract_all
from neuro.file_tags import CustomSong, DriveSong
from neuro.polars_utils import Preset, load_dates, load_db
from neuro.utils import MP3GainMode, MP3ModeTuple, format_logger, time_format, get_audio_hash_to_file_mapping

DateDict = dict[str, dict[str, str]]

g_hash_to_file_dict: dict[str, str] = []

def new_batch_detection() -> None:
    """Re-runs the song detection based on regex. Adds songs that aren't already in\
        the database in a JSON file for them to be reviewed.
    """
    format_logger(verbosity=5, log_file=LOG_DIR / "batches.log")
    # These 3 lines could be ine call, but it would just make the code less clear
    out = extract_all()  # Extracts data
    export_json(out)  # Writing into JSON

data_formats = ['ascii_data', 'utf8_data']

def generate_from_preset(preset: Preset, dates_dict: DateDict) -> None:
    """Generates all songs from a preset, filters songs that respect filters.

    Args:
        preset (Preset): Preset configuration.
        dates_dict (DateDict): Date dict to pass to drive song constructor.
    """

    global g_hash_to_file_dict

    if not len(g_hash_to_file_dict):
        g_hash_to_file_dict = get_audio_hash_to_file_mapping(SONG_ROOT_DIR)

    t = time()
    songs_filtered = preset.get_filtered_df()
    N_SONGS = 0  # Avoids error if no songs are found
    for i, song_dict in enumerate(songs_filtered.iter_rows(named=True)):
        N_SONGS = len(songs_filtered)

        # Differenciate songs from drive and custom songs. Mainly because they aren't
        # from the same contexts (streams vs collabs mainly). Their format is different.
        # Subathon mixes are put in custom, so drive songs are only mp3
        if Path(song_dict["File_IN"]).is_relative_to(DRIVE_DIR) or ((Path(song_dict["File_IN"]).is_relative_to(UNOFFICIALV3_DIR)) and (not Path(song_dict['File_IN']).is_relative_to(UNOFFICIALV3_DIR / UNOFFV3_DISC66))):
            date_dict = dates_dict.get(song_dict["Date"], {})
            s = DriveSong(song_dict, date_dict)
        # elif Path(song_dict["File_IN"]).is_relative_to(UNOFFICIALV3_DIR):
        #     s = UnofficialV3Song(song_dict, date_dict)
        else:
            s = CustomSong(song_dict)

        final_out_paths = {
            'song_files': {},
            'metadata_files': {},
            }
        if s.flags.originals or s.flags.official:
            final_out_paths['song_files']['ascii_data'] = Path(preset.root / 'official_releases/ascii_data' if preset.root is not None else 'official_releases/ascii_data') / preset.subdir
            final_out_paths['song_files']['utf8_data'] = Path(preset.root / 'official_releases/utf8_data' if preset.root is not None else 'official_releases/utf8_data') / preset.subdir

            final_out_paths['metadata_files']['ascii_data'] = Path(preset.root / 'unofficial_releases/ascii_data' if preset.root is not None else 'unofficial_releases/ascii_data') / preset.subdir
            final_out_paths['metadata_files']['utf8_data'] = Path(preset.root / 'unofficial_releases/utf8_data' if preset.root is not None else 'unofficial_releases/utf8_data') / preset.subdir
        else:
            final_out_paths['song_files']['ascii_data'] = Path(preset.root / 'unofficial_releases/ascii_data' if preset.root is not None else 'unofficial_releases/ascii_data') / preset.subdir
            final_out_paths['song_files']['utf8_data'] = Path(preset.root / 'unofficial_releases/utf8_data' if preset.root is not None else 'unofficial_releases/utf8_data') / preset.subdir

        for data_format in data_formats[0:1]:
            os.makedirs(final_out_paths['song_files'][data_format], exist_ok=True)
            if s.hash_in in g_hash_to_file_dict.keys():
                created = s.create_out_file(create=False, out_dir=final_out_paths['song_files'][data_format])
                if created:
                    s.apply_tags(data_format == 'ascii_data')
                logger.debug(f"[GEN] [{preset.name}] [{i + 1:3d}/{N_SONGS}] {'Generated' if created else 'Skipped'} {song_dict['Title']}")
                # if s.flags.official or s.flags.originals:
                    # os.makedirs(final_out_paths['metadata_files'][data_format], exist_ok=True)
                    # s.create_placeholder_files(out_dir=final_out_paths['metadata_files'][data_format])
            elif s.flags.official or s.flags.originals:
                logger.warning(f"[GEN] [{preset.name}] [{i + 1:3d}/{N_SONGS}] Skipped {song_dict['Title']} official song file not found: {song_dict['File_IN']}")
                # s.create_placeholder_files(out_dir=final_out_paths['song_files'][data_format])
                # s.create_placeholder_files(out_dir=final_out_paths['metadata_files'][data_format])
                continue
            else:
                logger.error(f"[GEN] [{preset.name}] [{i + 1:3d}/{N_SONGS}] ERROR {song_dict['Title']} unofficial song file not found: {song_dict['File_IN']}")
                exit(1)
    run_mp3gain(preset)
    logger.success(f"[GEN] Done converting {N_SONGS} songs in {time_format(time() - t)} !")


def generate_songs() -> None:
    """Generates all songs files. For each files it first copies the files into\
    its destination, then edits the metadata of the destination file. This is\
    just to avoid tempering the original files.\
    Generates songs in preset groups.
    """

    format_logger(log_file=LOG_DIR / "generation.log")
    logger.info("[GEN] Starting generation batch")

    # Avoids wrong generations due to inconsistent databases
    try:
        check_are_dbs_identical()
    except ValueError as e:
        logger.error("[GEN] Error while comparing Databases")
        raise e

    # Loading config file
    with open("config.toml", "rb") as file:
        config = toml.load(file)

    cfg_out = config["output"]
    if cfg_out["use-root"]:
        OUT_ROOT = Path(cfg_out["out-root"])
    else:
        OUT_ROOT = None

    mp3gain = parse_mp3gain(config)

    # Start time
    t = time()

    # Easier data format to deal with
    dates_dict: DateDict = {k["Date"]: k for k in load_dates().iter_rows(named=True)}

    for preset in config["Presets"]:
        logger.info(f"[GEN] Generating preset '{preset['name']}'")
        preset_obj = Preset(preset, mp3gain, OUT_ROOT)
        generate_from_preset(preset_obj, dates_dict)

    logger.success(f"[GEN] Generated all presets in {time_format(time() - t)} !")


def generate_albums() -> None:
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
    
    # Loading config file
    with open("config.toml", "rb") as file:
        config = toml.load(file)
    
    cfg_out = config["output"]
    if cfg_out["use-root"]:
        OUT_ROOT = Path(cfg_out["out-root"])
    else:
        OUT_ROOT = None

    mp3gain = parse_mp3gain(config)

    # Start time
    t = time()

    songDB = load_db()

    dates_dict: DateDict = {k["Date"]: k for k in load_dates().iter_rows(named=True)}
    
    for i, song_dict in enumerate(songDB.iter_rows(named=True)):
        N_SONGS = len(songDB)

        if Path(song_dict["File_IN"]).is_relative_to(DRIVE_DIR) or ((Path(song_dict["File_IN"]).is_relative_to(UNOFFICIALV3_DIR)) and (not Path(song_dict['File_IN']).is_relative_to(UNOFFICIALV3_DIR / UNOFFV3_DISC66))):
            date_dict = dates_dict.get(song_dict["Date"], {})
            s = DriveSong(song_dict, date_dict)
        else:
            s = CustomSong(song_dict)

        final_out_paths = {
            'song_files': {},
            'metadata_files': {},
            }

        album = s.album

    
        if s.flags.originals or s.flags.official:
            final_out_paths['song_files']['ascii_data'] = Path(str(OUT_ROOT) + '/official_releases/ascii_data/albums/' + album)
            final_out_paths['song_files']['utf8_data'] = Path(str(OUT_ROOT) + '/official_releases/utf8_data/albums/' + album)

            final_out_paths['metadata_files']['ascii_data'] = Path(str(OUT_ROOT) + '/unofficial_releases/ascii_data/albums/' + album)
            final_out_paths['metadata_files']['utf8_data'] = Path(str(OUT_ROOT) + '/unofficial_releases/utf8_data/albums/' + album)
        else:
            final_out_paths['song_files']['ascii_data'] = Path(str(OUT_ROOT) + '/unofficial_releases/ascii_data/albums/' + album)
            final_out_paths['song_files']['utf8_data'] = Path(str(OUT_ROOT) + '/unofficial_releases/utf8_data/albums/' + album)

        for data_format in data_formats[0:1]:
            os.makedirs(final_out_paths['song_files'][data_format], exist_ok=True)
            if s.hash_in in g_hash_to_file_dict.keys():
                created = s.create_out_file(create=False, out_dir=final_out_paths['song_files'][data_format], numberedFiles=True)
                if created:
                    s.apply_tags(data_format == 'ascii_data')
                logger.debug(f"[GEN] [{i+1:4d}/{N_SONGS}] [{album}] {'Generated' if created else 'Skipped'} {song_dict['Title']}")
                # if s.flags.official or s.flags.originals:
                    # os.makedirs(final_out_paths['metadata_files'][data_format], exist_ok=True)
                    # s.create_placeholder_files(out_dir=final_out_paths['metadata_files'][data_format], numberedFiles=True)
            elif s.flags.originals or s.flags.official:
                logger.warning(f"[GEN] [{i+1:4d}/{N_SONGS}] [{album}] Skipped {song_dict['Title']} official song file not found: {song_dict['File_IN']}")
                # s.create_placeholder_files(out_dir=final_out_paths['song_files'][data_format], numberedFiles=True)
                # s.create_placeholder_files(out_dir=final_out_paths['metadata_files'][data_format], numberedFiles=True)
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
    logger.info(f"[GEN] Running mp3gain for preset {preset.name}")
    options = ""
    if preset.mp3gain is MP3GainMode.GAIN:
        options = "-r -k"
    OUT_LOG = Path(LOG_DIR / "mpgain.log")
    os.system(f"mp3gain {options} {preset.path}/*.mp3 > {OUT_LOG}")


def mp3gain_standalone() -> None:
    """Runs mp3gain on all presets without creating the files"""
    format_logger(log_file=LOG_DIR / "generation.log")
    logger.info("[MP3G] Starting generation batch")

    # Loading config file
    with open("config.toml", "rb") as file:
        config = toml.load(file)

    cfg_out = config["output"]
    if cfg_out["use-root"]:
        OUT_ROOT = Path(cfg_out["out-root"])
    else:
        OUT_ROOT = None

    mp3gain = parse_mp3gain(config)

    for preset in config["Presets"]:
        logger.info(f"[MP3G] Generating preset '{preset['name']}'")
        preset_obj = Preset(preset, mp3gain, OUT_ROOT)
        run_mp3gain(preset_obj)


if __name__ == "__main__":
    generate_songs()
