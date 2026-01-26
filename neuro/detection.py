"""Detects new files and parse their data."""

import json
import re
from datetime import datetime
from dateutil.parser import parse
from pathlib import Path
from typing import Optional
import tinytag

import polars as pl
from loguru import logger

# TODO are the different unoffV3 subdirs actually needed, or just the root unoffV3 dir
from neuro import CUSTOM_DIR, DRIVE_DIR, ROOT_DIR, SONGS_JSON, UNOFFICIALV3_DIR, UNOFFV3_DISC1, UNOFFV3_DISC2, UNOFFV3_DISC3, UNOFFV3_DISC4, UNOFFV3_DISC5, UNOFFV3_DISC6, UNOFFV3_DISC7, UNOFFV3_DISC8, UNOFFV3_DISC66, OFFICIAL_RELEASE_DIR, SETLISTS_DIR
from neuro.polars_utils import load_db, load_dates
from neuro.utils import get_audio_hash

SongEntry = dict[str, Optional[str]]
"""Dictionary representing a song in the JSON, containing fields like "Song", "Artist", etc..."""
SongJSON = dict[str, list[SongEntry]]
"""Whole JSON file expected format. A list of date-indexed lists of songs."""


def get_files(songs: pl.DataFrame) -> dict[str, list[Path]]:
    """Gets filenames from expected directories. Skips files that are already in the database.\
        Check the function code to see which directories are searched through.

    Args:
        songs (pl.DataFrame): Songs database, here to check the current existing files.

    Returns:
        dict[str, list[Path]]: Audio files filtered by directories.\
            Keys: "Neuro", "Evil", "Duets", "V1", "V2", "Custom".
    """
    # Set of all files already treated and registered
    # TODO add error checking for if a empty entry was accidentally added to the DB
    # TODO switch to using audio hash to check if song is already in database
    existing = set(map(lambda x: ROOT_DIR / Path(x), songs.get_column("File_IN").to_list()))

    def get_audios(p: Path, *, filetype: str = "mp3") -> list[Path]:
        files = list(p.glob(f"*.{filetype}"))
        return list(filter(lambda f: f not in existing, files))

    neuro_dir = DRIVE_DIR
    duets_dir = DRIVE_DIR / "Duets"
    evil_dir = [DRIVE_DIR / "Evil", DRIVE_DIR / "Evil/QUARANTINE"]
    v1_dir = DRIVE_DIR / "v1 voice"
    v2_dir = DRIVE_DIR / "v2 voice"
    custom_dir = CUSTOM_DIR
    unofficialV3_dir = [UNOFFICIALV3_DIR / UNOFFV3_DISC1, UNOFFICIALV3_DIR / UNOFFV3_DISC2, UNOFFICIALV3_DIR / UNOFFV3_DISC3, UNOFFICIALV3_DIR / UNOFFV3_DISC4, UNOFFICIALV3_DIR / UNOFFV3_DISC5, UNOFFICIALV3_DIR / UNOFFV3_DISC6, UNOFFICIALV3_DIR / UNOFFV3_DISC7, UNOFFICIALV3_DIR / UNOFFV3_DISC8, UNOFFICIALV3_DIR / UNOFFV3_DISC66]

    return {
        "Neuro": get_audios(neuro_dir),
        "Evil": get_audios(evil_dir[0]) + get_audios(evil_dir[1]),
        "Duets": get_audios(duets_dir),
        "V1": get_audios(v1_dir),
        "V2": get_audios(v2_dir),
        "Custom": get_audios(custom_dir) + get_audios(custom_dir, filetype="flac"),
        "UnofficialV3": get_audios(unofficialV3_dir[0]) + get_audios(unofficialV3_dir[1]) + get_audios(unofficialV3_dir[2]) + get_audios(unofficialV3_dir[3]) + get_audios(unofficialV3_dir[4]) + get_audios(unofficialV3_dir[5]) + get_audios(unofficialV3_dir[6]) + get_audios(unofficialV3_dir[7]) + get_audios(unofficialV3_dir[8]),
    }


def get_regexes() -> dict[str, list[str]]:
    """Gets different patterns as lists to match all cases of filenames. Check function code \
        to see which patterns are used. The patterns are made to be from the most selective to the least.

    Returns:
        dict[str, list[str]]: Lists of patterns grouped by use cases: common, evil, v1.\
            v2 can use common. custom can use common.
    """
    # Naming regex groups to ease treatment
    TITLE_FULL = "(?P<art>.+) - (?P<song>.+)"
    TITLE_PART = "(?P<full>.+)"
    EVIL = r"\(evil\)"
    DATE = r"\((?P<date>\d\d \d\d \d\d)\)"
    EXT = r"\.(?:mp3|wav)"
    common = [
        f"{TITLE_FULL} {DATE}{EXT}",
        f"{TITLE_PART} {DATE}{EXT}",
        f"{TITLE_FULL}{EXT}",
        f"{TITLE_PART}{EXT}",
    ]
    evil = [
        f"{TITLE_FULL} {DATE} {EVIL}{EXT}",
        f"{TITLE_FULL} {EVIL} {DATE}{EXT}",
        f"{TITLE_FULL} {EVIL}{EXT}",
        f"{TITLE_PART} {DATE} {EVIL}{EXT}",
        f"{TITLE_PART} {EVIL} {DATE}{EXT}",
        f"{TITLE_PART} {EVIL}{EXT}",
    ]
    DATE_V1 = r"\[(?P<date_v1>\d\d[-／]\d\d[-／]\d\d)\]"
    RANDOM_HASH_WTF = r"\[\d+\]"  # Some v1 songs have some sort of hash...
    v1 = [
        f"{DATE_V1} {TITLE_PART} {RANDOM_HASH_WTF}{EXT}",
        f"{DATE_V1} {TITLE_PART}{EXT}",
    ]
    return {"Neuro": common, "Evil": evil, "v1": v1}

# def get_unofficialV3_regexes() -> dict[str, list[str]]:
#     """gets the regexes to match filenames in unofficial archive v3
    
#     Returns:
#         dict[str, list[str]]: list of patterns
#     """
#     V1V2 = r"\d+\. (?P<art>.+) - (?P<song>.+) \(Neuro\.v(?P<neuro_ver>\d)\)\.mp3"
#     V3 = r"\d+\. (?P<art>.+) - (?P<song>.+) (\((?P<singer>.+)\..*\))\.mp3"
#     DUET = r"\d+\. (?P<art>.+) - (?P<song>.+) (\(Duet.+\)) \((?P<singer>(Neuro|Evil) & (Neuro|Evil))\)\.mp3"
#     COLLAB = r"\d+\. (?P<art>.+) - (?P<song>.+) (\(Duet.+\)) \((?P<singer>(Neuro|Evil) & (?!(Neuro|Evil)).+)\)\.mp3"
#     SUBATHON_REMIX = r"\d+. Mixed by (?P<mixer>QueenPb) - (?P<song>Anniversary Mashup \(\d{4}\)) \(Duet.v\d\) \((?P<singers>.+)\).mp3"


def get_artist_and_title(groups: dict[str, str]) -> tuple[str, str]:
    """Returns song title and artist extracted from a filename using regexes.

    Args:
        groups (dict[str, str]): Groups obtained by matching a pattern with filename.\
            Groups must be named, obtained with `groupdicts`.

    Returns:
        tuple[str, str]: Tuple (artist, song). If the title has no "-", then the only field.\
            Is considered to be the song name.
    """
    artist = groups.get("art", "")
    song = groups.get("song", "")

    if "full" in groups.keys():  # Title with no dash or not detected
        full = groups["full"]
        if "-" in full:
            artist, song = full.split("-")
        else:
            song = full
    return (artist.strip(), song.strip())  # Removes possible spaces around


def get_date(groups: dict[str, str]) -> str:
    """Formats the date obtained via regex to a unique format YYYY-MM-DD.\
        The v1 dates are treated separately because they don't use the same format.

    Args:
        groups (dict[str, str]): Groups obtained by matching a pattern with filename.\
            Groups must be named, obtained with `groupdicts`.

    Returns:
        str: The date with YYYY_MM_DD format. If no date was provided via regex, "outlier"\
            is returned.
    """
    y, m, d = "", "", ""  # Avoids unbound variable error
    if "date_v1" in groups:  # v1 are M/D/Y
        date_pat = groups["date_v1"]
        if "-" in date_pat:
            m, d, y = date_pat.split("-")
        if "／" in date_pat:  # For that one v1 song that uses this annoying character...
            m, d, y = date_pat.split("／")
    elif "date" in groups:  # v3 are D/M/Y
        date_pat = groups["date"]
        d, m, y = date_pat.split(" ")
    else:  # "date" not in groups:
        return "outlier"
    dt = datetime(year=2000 + int(y), month=int(m), day=int(d))
    date = dt.strftime(r"%Y-%m-%d")
    return date


def extract_common(file: Path, regexes: list[str]) -> tuple[str, SongEntry]:
    """Tries to find a regex pattern to match a file structure to extract data.\
        Function applied to drive files mostly.

    Args:
        file (Path): File concerned.
        regexes (list[str]): List of regex patterns to try to match.

    Raises:
        ValueError: If none of the patterns matched.

    Returns:
        tuple[str, SongEntry]: A tuple with the 'date' (can be "outlier") and the main info\
            about the song: artist, song title, the original file and an album id.
    """
    data, date = {}, ""  # Avoids unbound variable error
    for i, pat in enumerate(regexes):
        matched = re.match(pat, str(file.name))
        if matched is None:
            continue
        logger.debug(f"File '{file.name}' matched pattern {i}")

        groups = matched.groupdict()
        artist, song = get_artist_and_title(groups)

        date = get_date(groups)
        if date == "outlier":
            logger.warning(f"File '{file.name} is an outlier")

        data = {
            "Artist": artist,
            "Song": song,
            "file": str(file),
            "id": None,
        }
        break  # Once a pattern matched, we stop looking for one
    if data == {}:  # Date is always assigned if a pattern matched
        logger.error(f"Couldn't find match for file '{file}'")
        raise ValueError
    return date, data


def extract_list(files: list[Path], regexes: list[str], out: SongJSON = {}) -> SongJSON:
    """Applies `extract_common` to a list of files and group them by date in a dictionary.

    Args:
        files (list[Path]): List of files to treat.
        regexes (list[str]): List of regex patterns.
        out (SongJSON, optional): Output dictionary, if no dictionary is passed, it's created\
            and returned. But an existing one can be passed to be completed. Defaults to {}.

    Returns:
        SongJSON: The output dict completed with the list of files' information.
    """
    for file in files:
        date, data = extract_common(file, regexes)
        if date in out:
            out[date].append(data)
        else:
            out[date] = [data]
    return out


def extract_custom(files: list[Path], out: SongJSON = {}) -> SongJSON:
    """Function on the same level as `extract_list`, but specialized for treatment of \
        custom files.

    Args:
        files (list[Path]): List of files.
        out (SongJSON, optional): Same as for `extract_list`. Dictionary created or completed\
            with files' data. Defaults to {}.

    Returns:
        SongJSON: Dictionary with at least these files' information.
    """
    outputs = []
    for file in files:
        filename = file.stem
        # We can require this format for custom songs as the filename is chosen
        try:
            artist, song = map(str.strip, filename.split(" - "))
        except ValueError:
            logger.warning(f"Couldn't extract artist - song pattern for {file}")
            artist = ""
            song = filename
        data = {
            "Artist": artist,
            "Song": song,
            "file": str(file),
            "id": None,
        }
        outputs.append(data)
    out["custom"] = outputs
    return out

def extract_unofficialV3(files: list[Path], out: SongJSON = {}) -> SongJSON:
    """extract files from the Unofficial Neuro Karaoke Archvie v3
    
    Args:
        files (list[Path]): List of files.
        out (SongJSON, optional): Same as for `extract_list`. Dictionary created or completed\
            with files' data. Defaults to {}.
            
    Returns:
        SongJSON: Dictionary with at least these files' information.
    """

    id = 1
    for file in files:
        data = {}
        date = ""
        artist = ""
        title = ""
        trackInfo = tinytag.TinyTag.get(file)
        if 'comment' in trackInfo.other.keys():
            trackJSon = json.loads(trackInfo.other['comment'][0])
            input_date = parse(trackJSon['Date'])
            date = input_date.strftime("%Y-%m-%d")
            artist = trackJSon['Artist']
            title = trackJSon['Title']
        elif 'Mashup' in str(file):
            year = str(trackInfo.year)
            date = year + '-12-19'
            title = 'Anniversary Mashup (' + year + ')'
            artist = 'Duet (Neuro & Evil) - Mixed by QueenPb'
        elif 'ARG' in str(file):
            date = 'Neuro-sama ARG'
            artist = trackInfo.artist
            title = trackInfo.title
        data = {
            'Cover Artist' : trackJSon['CoverArtist'],
            'Artist' : artist,
            'Artist ASCII' : artist,
            'Song' : title,
            'Song ASCII' : title,
            'file' : str(file),
            'id' : id,
            'duplicate' : False,
        }
        # if date.__contains__("2023-01"):
        #     date = "Neuro [v1] January Stream Songs"
        # if date.__contains__("2023-02"):
        #     date = "Neuro [v1] Feburary Stream Songs"
        # if date.__contains__("2023-03") and date < "2023-03-22":
        #     date = "Neuro [v1] March Stream Songs"
        # unused song from PBs drive, was inserted into Disc 3 of Unofficial Archive, not including in Neuro-Sings
        # if (date == "2023" and title == "It's Been So Long") or (date == ""):
        #     date = "outlier"
        #     data['id'] = None
        # else:
        id += 1
        # date = "unofficial V3 extract"
        if date in out:
            out[date].append(data)
        else:
            out[date] = [data]

    return out

def parse_setlist(p: Path) -> SongJSON:
    with open(p, 'r') as file:
        lines = file.readlines()

    songs: SongJSON = {}
    
    print("lines")
    print(lines)

    print('\nfields')

    is_album_info_line = False
    is_singer_change_line = False
    is_song_line = False

    found_album_line = False

    lead_singer = "Neuro"
    album_art = None

    dates_df = load_dates()

    for line in lines:
        fields = line.strip('\n').split(' | ')
        print(fields)

        date_format = "%Y-%m-%d"
        try:
            is_album_info_line = bool(datetime.strptime(fields[0], date_format))
            print(fields[0])
            print("album info line")
        except:
            is_album_info_line = False


        if not is_album_info_line and (fields[0] == "Neuro" or fields[0] == "Evil"):
            is_singer_change_line = True
            print("singer change line")
        else:
            is_singer_change_line = False

        if (not is_album_info_line) and (not is_singer_change_line):
            is_song_line = True
            print("song line")
        else:
            is_song_line = False

        
        if is_album_info_line:
            print("album info line")
            album_art = None # reset album cover art to None
            # if len(fields) == 1:
            #     raise ValueError()
            # TODO input validation
            input_date = parse(fields[0])
            date = input_date.strftime(date_format)
            singer = fields[1]
            if date in dates_df.get_column("Date"):
                continue
            if len(fields) == 2:
                # need to know singer to name karaoke stream albums, but current setlist format has singer changes on seperate line from date and album title
                # solution, add singer as second field of album info line
                album = f"{singer} {date} Karaoke"
                songs[album] = []
            else:
                album = fields[2]
                songs[album] = []
            if len(fields) == 4:
                album_art = fields[3]
            found_album_line = True
            continue
        
        if is_singer_change_line and found_album_line:
            print("singer change line")
            lead_singer = fields[0]

        if is_song_line and found_album_line:
            # TRACK# | SONG_TITLE | ARTIST | COVER_ARTIST | NEW/DUPLICATE | SONG_COVER_ART(OPTIONAL)
            song_art = None # reset song specific art to None
            print("song line")
            id = int(fields[0])
            song_title = fields[1]
            artist = fields[2]
            cover_artist = fields[3]
            if fields[4].lower() == "new":
                dupe = False
            else:
                dupe = True
            if len(fields) == 6:
                song_art = fields[5]
            else:
                song_art = album_art
            print(song_art)
            data = {
                'Artist': artist,
                'Artist ASCII': artist,
                'Song': song_title,
                'Song ASCII': song_title,
                'Cover Artist': lead_singer,
                'Image' : song_art,
                'Date' : date,
                'id': id,
                'duplicate': dupe,
            }
            songs[album].append(data)

    print(songs)
    return songs

    # TODO error checking

    # add way to tag which outfit/hairstyle each singer is wearing
    # add way to tag if stream was a 2d or 3d stream

def song_entry_sort_by_id(e):
    return e['id']


def fill_in_duplicates(out: SongJSON = {}) -> SongJSON:
    # check if a setlist file with a date not already in dates exists
    # check each existing entry under the date in out:SongJSON, and update "id", removing those entries from the in-memory copy of the setlist
    # for each remaining entry in the setlist, create a duplicate entry using the most recent version of the song from the same singer from the setlist date or before

    # keep track of which setlist files have been seen before

    dates_df = load_dates()

    files = list(SETLISTS_DIR.glob(f"*.txt"))

    format = "%Y-%m-%d"

    for file in files:
        file_stem = file.stem
        res = True
        try:
            date = parse(file_stem, fuzzy=True).strftime(format)
        except ValueError:
            res = False

        print(date)

        if not res:
            # TODO log "file " + str(file) + " does not match expected naming convention, skipping"
            continue

        if date in dates_df.get_column("Date"):
            # TODO log f"date from filename {date} is already in dates table"
            continue
        
        albums = parse_setlist(file)

        for album, songs in albums.items():
            # TODO actually insert duplicate songs into SongJSON out

            if album not in out.keys() and date in out.keys():
                out[album] = out.pop(date)
            
            found_ids = []

            for song in out[album]:
                for entry in albums[album]:
                    if song['Artist'] == entry['Artist'] and song['Song'] == entry['Song']:
                        song['id'] = entry['id']
                        found_ids.append(entry["id"])
                        print(entry)

            print(found_ids)

            out[album].sort(key=song_entry_sort_by_id)
            
            for entry in albums[album]:
                print(entry)
                if entry["id"] not in found_ids:
                    out[album].insert((entry["id"]-1), entry)
                else:
                    out[album][entry['id']- 1 ]['Date'] = entry['Date']
                    out[album][entry['id']- 1 ]['id'] = entry['id']
                    if entry['Image'] is not None:
                        out[album][entry['id']- 1 ]['Image'] = entry['Image']
                    else:
                        out[album][entry['id']- 1 ]['Image'] = art

                print(out[album][entry['id']- 1 ])

            out[album].sort(key=song_entry_sort_by_id)

    return out

def extract_all() -> SongJSON:
    """Runs all the extraction functions on all defined patterns.

    Returns:
        SongJSON: Output dictionary containg all files that are not yet in the database.\
            They are grouped by date, or category if no date was provided in filename.
    """
    songs_db = load_db()
    files = get_files(songs_db)
    regex = get_regexes()

    out: SongJSON = {}
    # Neuro
    # extract_list(files["Neuro"], regex["Neuro"], out)
    # Evil
    # extract_list(files["Evil"], regex["Evil"], out)
    # Duets
    # extract_list(files["Duets"], regex["Neuro"], out)

    # v1
    # extract_list(files["V1"], regex["v1"], out)
    # v2
    # extract_list(files["V2"], regex["Neuro"], out)

    # Custom
    extract_custom(files["Custom"], out)

    # unofficial v3
    extract_unofficialV3(files["UnofficialV3"], out)
    fill_in_duplicates(out)

    # TODO attempt to automatically strip non-ASCII characters from the _ASCII fields

    if len(out["custom"]) == 0:
        out.pop("custom")

    return out


def export_json(all_songs: SongJSON) -> None:
    """Takes an existing result of new files search and exports it in a json file.

    Args:
        all_songs (SongJSON): Dictionary with lists of files grouped by date.
    """
    songs = {}
    # Sorting songs by date for easier treatment
    for k in sorted(list(all_songs.keys())):
        songs[k] = all_songs[k]

    with open(SONGS_JSON, "w") as f:
        json.dump(songs, f, indent=2, ensure_ascii=False)
        f.write("\n")
