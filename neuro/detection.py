"""Detects new files and parse their data."""

import json
import re
from datetime import datetime
from dateutil.parser import parse
from pathlib import Path
import tinytag

import polars as pl
from loguru import logger

# TODO are the different unoffV3 subdirs actually needed, or just the root unoffV3 dir
from neuro import CUSTOM_DIR, ROOT_DIR, SONGS_JSON, UNOFFICIALV3_DIR, UNOFFV3_DISC1, UNOFFV3_DISC2, UNOFFV3_DISC3, UNOFFV3_DISC4, UNOFFV3_DISC5, UNOFFV3_DISC6, UNOFFV3_DISC7, UNOFFV3_DISC8, UNOFFV3_DISC66, OFFICIAL_RELEASE_DIR, SETLISTS_DIR, OFFICIAL_CSV, ORIGINAL_CSV
from neuro.polars_utils import load_db, load_dates
import neuro.utils as neutils

karaoke_album_title_regex = r'(Neuro|Evil|Twins) \d{4}(-\d{1,2}){2} (Mini-)?Karaoke'
song_line_regex = r'^\d{1,} *\|'
date_regex = r'\d{4,}\-\d\d?\-\d\d?'

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
        if len(files) == 0:
            logger.warning(f"no files found in {p} of filetype {filetype}")
        return list(filter(lambda f: f not in existing, files))

    custom_dir = CUSTOM_DIR
    unofficialV3_dir = [UNOFFICIALV3_DIR / UNOFFV3_DISC1, UNOFFICIALV3_DIR / UNOFFV3_DISC2, UNOFFICIALV3_DIR / UNOFFV3_DISC3, UNOFFICIALV3_DIR / UNOFFV3_DISC4, UNOFFICIALV3_DIR / UNOFFV3_DISC5, UNOFFICIALV3_DIR / UNOFFV3_DISC6, UNOFFICIALV3_DIR / UNOFFV3_DISC7, UNOFFICIALV3_DIR / UNOFFV3_DISC8]
    arg_dir = UNOFFICIALV3_DIR / UNOFFV3_DISC66
    official_dir = OFFICIAL_RELEASE_DIR

    return {
        "Custom": get_audios(custom_dir) + get_audios(custom_dir, filetype="flac"),
        "UnofficialV3": get_audios(unofficialV3_dir[0]) + get_audios(unofficialV3_dir[1]) + get_audios(unofficialV3_dir[2]) + get_audios(unofficialV3_dir[3]) + get_audios(unofficialV3_dir[4]) + get_audios(unofficialV3_dir[5]) + get_audios(unofficialV3_dir[6]) + get_audios(unofficialV3_dir[7]),
        "ARG": get_audios(arg_dir),
        "Official": list(official_dir.glob(f"*/**/*.mp3")), # search in all subdirectories recursively, can't use this glob pattern for UnofficialV3 as that would also get the ARG songs a second time
    }


def get_regexes() -> dict[str, list[str]]:
    """Gets different patterns as lists to match all cases of filenames. Check function code \
        to see which patterns are used. The patterns are made to be from the most selective to the least.

    Returns:
        dict[str, list[str]]: Lists of patterns grouped by use cases: common, evil, v1.\
            v2 can use common. custom can use common.
    """
    # Naming regex groups to ease treatment
    TITLE_FULL = "(?P<art>.+) - (?P<title>.+)"
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
    title = groups.get("title", "")

    if "full" in groups.keys():  # Title with no dash or not detected
        full = groups["full"]
        if "-" in full:
            artist, title = full.split("-")
        else:
            title = full
    return (artist.strip(), title.strip())  # Removes possible spaces around


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


def extract_common(file: Path, regexes: list[str]) -> tuple[str, neutils.SongEntry]:
    """Tries to find a regex pattern to match a file structure to extract data.\
        Function applied to drive files mostly.

    Args:
        file (Path): File concerned.
        regexes (list[str]): List of regex patterns to try to match.

    Raises:
        ValueError: If none of the patterns matched.

    Returns:
        tuple[str, SongEntry]: A tuple with the 'Date' (can be "outlier") and the main info\
            about the song: artist, song title, the original file and an album id.
    """
    data, date = {}, ""  # Avoids unbound variable error
    for i, pat in enumerate(regexes):
        matched = re.match(pat, str(file.name))
        if matched is None:
            continue
        logger.debug(f"File '{file.name}' matched pattern {i}")

        groups = matched.groupdict()
        artist, title = get_artist_and_title(groups)

        date = get_date(groups)
        if date == "outlier":
            logger.warning(f"File '{file.name} is an outlier")

        data = {
            "Artist": artist,
            "Title": title,
            "File_IN": str(file),
            "id": None,
        }
        break  # Once a pattern matched, we stop looking for one
    if data == {}:  # Date is always assigned if a pattern matched
        logger.error(f"Couldn't find match for file '{file}'")
        raise ValueError
    return date, data


def extract_list(files: list[Path], regexes: list[str], out: neutils.SongJSON = {}) -> neutils.SongJSON:
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


def extract_custom(files: list[Path], out: neutils.SongJSON = {}) -> neutils.SongJSON:
    """Function on the same level as `extract_list`, but specialized for treatment of \
        custom files.

    Args:
        files (list[Path]): List of files.
        out (SongJSON, optional): Same as for `extract_list`. Dictionary created or completed\
            with files' data. Defaults to {}.

    Returns:
        SongJSON: Dictionary with at least these files' information.
    """

    # there are a lot less custom songs, since most of the ones that were are included in the Unofficial Archive that is the new source for mp3 files
    # print(files)
    for file in files:
        # print(file)
        filename = file.stem
        fields = filename.split(' - ')
        artist = fields[0]
        title = fields[1]
        cover_artist = fields[2]
        album = fields[3]
        
        # TODO print reminder to check artist, title, identify for custom songs
        data = {
            "Artist": artist,
            "ArtistOG": "None",
            "Title": title,
            "TitleOG": "None",
            "Identify": "None",
            "Cover Artist": cover_artist,
            "File_IN": str(file),
            "id": 999999,
            # 'Date': "1970-01-01",
            'Version': None,
            'Hash_IN': neutils.get_audio_hash(Path(file)),
        }

        if album in out.keys():
            out[album].append(data)
        else:
            out[album] = [data]

    # for album in out.keys():
    #     for song in out[album]:
    #         print(song)
    # exit()

    return out

def extract_unofficialV3(files: list[Path], out: neutils.SongJSON = {}) -> neutils.SongJSON:
    """extract files from the Unofficial Neuro Karaoke Archvie v3
    
    Args:
        files (list[Path]): List of files.
        out (SongJSON, optional): Same as for `extract_list`. Dictionary created or completed\
            with files' data. Defaults to {}.
            
    Returns:
        SongJSON: Dictionary with at least these files' information.
    """

    songs_df = load_db()

    id = 1
    for file in files:
        if neutils.get_audio_hash(file) in songs_df.get_column('Hash_IN'):
            continue
        data = {}
        date = ""
        artist = ""
        artist_og = ""
        title = ""
        title_og = ""
        identify = ""
        trackInfo = tinytag.TinyTag.get(file)
        # print("")
        # print("")
        # print(file)
        # print(trackInfo.comment)
        # print(trackInfo.other.keys())
        # for key in trackInfo.other.keys():
            # print(key)
            # print(trackInfo.other[key])
        if len(trackInfo.comment) > 0 and trackInfo.comment.startswith('{') and trackInfo.comment.endswith('}'):
            trackJSon = json.loads(trackInfo.comment)
            input_date = parse(trackJSon['Date'])
            date = input_date.strftime("%Y-%m-%d")
            artist = trackJSon['Artist']
            artist_og = trackJSon['ArtistOG']
            title = trackJSon['Title']
            title_og = trackJSon['TitleOG']
            identify = trackJSon['Identify']
        elif 'comment' in trackInfo.other.keys():
            found_json = False
            # print("")
            # print(trackInfo.other['comment'])
            assert len(trackInfo.other['comment'])
            for comment in trackInfo.other['comment']:
                # print("")
                # print(comment)
                if comment.startswith('{') and comment.endswith('}'):
                    trackJSon = json.loads(comment)
                    found_json = True
            assert found_json
            input_date = parse(trackJSon['Date'])
            date = input_date.strftime("%Y-%m-%d")
            artist = trackJSon['Artist']
            artist_og = trackJSon['ArtistOG']
            title = trackJSon['Title']
            title_og = trackJSon['TitleOG']
            identify = trackJSon['Identify']
        cover_artist = trackJSon['CoverArtist']
        version = trackJSon['Version']
        if cover_artist.startswith('Neuro') and (not cover_artist.startswith('Neuro &')) and version.startswith('1'):
            cover_artist = 'Neuro [v1]'
        elif cover_artist.startswith('Neuro') and (not cover_artist.startswith('Neuro &')) and version.startswith('2'):
            cover_artist = 'Neuro [v2]'
        if 'Neuro' in cover_artist and 'Annytf' in cover_artist and 'Seishun Complex' in title:
            cover_artist = 'Neuro [v2] & Annytf'
        data = {
            'Cover Artist' : cover_artist,
            'Artist' : artist,
            'ArtistOG' : artist_og,
            'Title' : title,
            'TitleOG' : title_og,
            'Identify' : identify,
            'File_IN' : str(file),
            'id' : id,
            'duplicate' : False,
            'Date' : date,
            'Lead Singer': cover_artist,
            'additional flags': "",
            'Version': version,
            'Hash_IN': neutils.get_audio_hash(Path(file)),
        }
        id += 1
        if date in out:
            out[date].append(data)
        else:
            out[date] = [data]

    return out

def extract_arg(files: list[Path], out: neutils.SongJSON = {}) -> neutils.SongJSON:
    id = 1
    for file in files:
        title = file.stem[4:]
        artist = 'Study-sama'
        duplicate = False
        trackInfo = tinytag.TinyTag.get(file)
        date = trackInfo.comment
        # print(date)

        data = {
            'Cover Artist' : artist,
            'Artist' : artist,
            'ArtistOG' : "None",
            'Title' : title,
            'TitleOG' : "None",
            'Identify' : "None",
            'File_IN' : str(file),
            'id' : id,
            'duplicate' : duplicate,
            'Date' : date,
            'Lead Singer': artist,
            'additional flags': "",
            'Version': '66',
            'Hash_IN': neutils.get_audio_hash(Path(file)),
        }

        if 'Neuro-sama ARG' in out.keys():
            out['Neuro-sama ARG'].append(data)
        else:
            out['Neuro-sama ARG'] = [data]
        id += 1

    return out

def extract_official(files: list[Path], out: neutils.SongJSON ={}) -> neutils.SongJSON:
    # load original_songs.csv and official_covers.csv
    # search files for each song
    official_songs_csv = pl.read_csv(OFFICIAL_CSV, separator='|').to_dicts()
    original_songs_csv = pl.read_csv(ORIGINAL_CSV).to_dicts()

    songs_db = load_db()
    
    # TODO figure out why the artist order matters for official covers

    id = 1

    for song in official_songs_csv:
        for file in files:
            if str(file) in songs_db['File_IN']:
                continue
            # print(file)
            # print(song)
            # print(f'{str(do_song_titles_match(file.stem, song['Title']))}')
            # print(f'{str(do_song_titles_match(song['Title'], file.stem))}')
            # need to try both orders because for some reason the mp3 file of CFRB is named 'Robot Body.mp3'
            if neutils.do_song_titles_match(file.stem, song['Title']) or neutils.do_song_titles_match(song['Title'], file.stem):
                artist = song['Artist']
                cover_artist = song['Cover Artist']
                title = song['Title']
                date = song['Date']
                # a lot of the code assumes that Neuro and Evil are the only singers, and only one, so for now one of them needs to be the lead singer
                if 'Neuro' in song['Cover Artist'] and 'Evil' in song['Cover Artist']:
                    lead_singer = 'Neuro'
                elif 'Neuro' in song['Cover Artist']:
                    lead_singer = 'Neuro'
                elif 'Evil' in song['Cover Artist']:
                    lead_singer = 'Evil'
                else:
                    print('how did we get here: neuro/detection.py:423')
                    print(song['Cover Artist'])
                    exit(1)
                if title == 'Chinatown Blues':
                    version = '2'
                else:
                    version = '1'
                data = {
                    'Cover Artist' : cover_artist,
                    'Artist' : artist,
                    'ArtistOG' : "None",
                    'Title' : title,
                    'TitleOG' : "None",
                    'Identify' : "None",
                    'File_IN' : str(file),
                    'id' : id,
                    'Date' : date,
                    'Lead Singer': lead_singer,
                    'additional flags': "",
                    'Version': version,
                    'Hash_IN': neutils.get_audio_hash(Path(file)),
                    }
                if 'custom' in out.keys():
                    out['custom'].append(data)
                else:
                    out['custom'] = [data]
                id += 1
        # TODO print reminder to check title, artist, identify for official songs

    for song in original_songs_csv:
        for file in files:
            if str(file) in songs_db['File_IN']:
                continue
            # print(file)
            # print(song)
            # print(f'{str(do_song_titles_match(file.stem, song['Title']))}')
            # print(f'{str(do_song_titles_match(song['Title'], file.stem))}')
            if neutils.do_song_titles_match(file.stem, song['Title']) or neutils.do_song_titles_match(song['Title'], file.stem):
                artist = song['Artist']
                cover_artist = artist
                title = song['Title']
                date = song['Date']
                data = {
                    'Cover Artist' : cover_artist,
                    'Artist' : artist,
                    'ArtistOG' : "None",
                    'Title' : title,
                    'TitleOG' : "None",
                    'Identify' : "None",
                    'File_IN' : str(file),
                    'id' : id,
                    'Date' : date,
                    'Lead Singer': artist,
                    'additional flags': "",
                    'Version': '1',
                    'Hash_IN': neutils.get_audio_hash(Path(file)),
                    }
                if 'custom' in out.keys():
                    out['custom'].append(data)
                else:
                    out['custom'] = [data]
                id += 1

    # for album in out.keys():
    #     print(album)
    #     for song in out[album]:
    #         print(song)
    # exit()
    return out

def parse_setlist(p: Path) -> neutils.SongJSON:
    with open(p, 'r') as file:
        lines = file.readlines()

    logger.info(f'parsing setlist {p.name}')

    songs: neutils.SongJSON = {}
    
    # print("lines")
    # print(lines)

    # print('\nfields')

    is_album_info_line = False
    is_singer_change_line = False
    is_song_line = False

    found_album_line = False
    album = ''

    lead_singer = "Neuro"
    album_art = None

    dates_df = load_dates()

    album_song_count = 0

    for line in lines:
        if re.match(song_line_regex, line) is not None:
            album_song_count += 1

    for line in lines:
        if line.startswith('!!'):
            continue # this is a comment line, do not process
        fields = line.strip('\n').split('|')
        fields = [f.strip() for f in fields]
        # print(fields)

        date_format = "%Y-%m-%d"
        try:
            is_album_info_line = bool(datetime.strptime(fields[0], date_format))
            # print(fields[0])
            # print("album info line")
        except:
            is_album_info_line = False


        # checking if starts with "Neuro" because 2026-04-01 April Fools karaoke included a song using v1 voice
        if not is_album_info_line and (fields[0].startswith("Neuro") or fields[0] == "Evil"):
            is_singer_change_line = True
            # print("singer change line")
        else:
            is_singer_change_line = False

        if (not is_album_info_line) and (not is_singer_change_line):
            is_song_line = True
            # print("song line")
        else:
            is_song_line = False

        
        if is_album_info_line:
            # print("album info line")
            input_date = parse(fields[0])
            date = input_date.strftime(date_format)
            if len(fields) == 1:
                if found_album_line == False:
                    print('first album info line only has date field')
                    print(p)
                    exit(1)
                else:
                    continue
            else:
                album_art = None # reset album cover art to None
                singer = fields[1]
                lead_singer = singer
                # print(fields[1])
                # if date in dates_df.get_column("Date"):
                    # continue
                    # TODO check if song is in database with the same date, and only if it isn't, add the setlist entry to the json
                    # print("placeholder code")
                # print(len(fields))
                if len(fields) < 2:
                    logger.error("not enough fields in album info line in setlist file: " + str(p))
                    exit(1)
                if len(fields) == 2:
                    if album_song_count < 17:
                        album = f"{singer} {date} Mini-Karaoke"
                    else:
                        album = f"{singer} {date} Karaoke"
                    # print(album)
                elif len(fields) >= 3 and not fields[2] == '':
                    album = fields[2]
                    # print(album)
                else:
                    if album_song_count < 17:
                        album = f"{singer} {date} Mini-Karaoke"
                    else:
                        album = f"{singer} {date} Karaoke"
                    # print(album)
                if album not in songs.keys():
                    # print('adding album to songs: ' + album)
                    songs[album] = []
                if len(fields) >= 4:
                    album_art = fields[3]
                found_album_line = True
                continue
        
        if is_singer_change_line and found_album_line:
            # print("singer change line")
            lead_singer = fields[0]
            continue

        if is_song_line and found_album_line:
            # print(fields)
            # TRACK# | SONG_TITLE | ARTIST | COVER_ARTIST | NEW/DUPLICATE | SONG_COVER_ART(OPTIONAL) | additional flags
            song_art = None # reset song specific art to None
            # print("song line")
            id = int(fields[0])
            song_title, identify = neutils.split_title_and_identify(fields[1])
            # print(fields[1])
            # print(song_title)
            # print(identify)
            artist = fields[2]
            if not fields[3] == '':
                cover_artist = fields[3]
            else:
                cover_artist = lead_singer
            dupe = False
            encore = False
            # print("fields[4]: " + fields[4])
            
            if fields[4].lower() == "new":
                dupe = False
            elif fields[4].lower() == "encore":
                dupe = True
                encore = True
            else:
                dupe = True
            
            if len(fields) >= 6 and not fields[5] == '':
                song_art = fields[5]
            else:
                song_art = album_art

            if len(fields) >= 7:
                additionalFlags = fields[6]
            else:
                additionalFlags = ''

            # print(song_art)
            data = {
                'Artist': artist,
                'ArtistOG': "",
                'Title': song_title,
                'TitleOG': "",
                'Identify': identify,
                'Cover Artist': cover_artist, # all singers on song
                'Lead Singer' : lead_singer, # the lead singer of the karaoke stream, used for assigning cover art for duets
                'Image': song_art,
                'Date': date,
                'id': id,
                'duplicate': dupe,
                'encore': encore,
                'additional flags': additionalFlags,
                'Version': None,
            }
            # print(album)
            songs[album].append(data)

    non_karaoke_albums = neutils.get_non_karaoke_album_names()
    if album not in non_karaoke_albums:
        twin_duet_stream = True
    else:
        twin_duet_stream = False

    if twin_duet_stream:
        for song in songs[album]:
            twin_duet_stream = twin_duet_stream and song['Cover Artist'] == 'Neuro & Evil'
            if not twin_duet_stream:
                break
    
    if twin_duet_stream:
        twin_album_stream_title = album.replace('Neuro', 'Twins').replace('Evil', 'Twins')
        songs[twin_album_stream_title] = songs.pop(album)

    # print(songs)
    return songs

    # TODO error checking

    # add way to tag which outfit/hairstyle each singer is wearing
    # add way to tag if stream was a 2d or 3d stream

def song_entry_sort_by_id(e):
    if e['id'] is None:
        return 999999
    return e['id']



def fill_in_setlists(out: neutils.SongJSON = {}) -> neutils.SongJSON:
    # check if a setlist file with a date not already in dates exists
    # check each existing entry under the date in out:SongJSON, and update "id", removing those entries from the in-memory copy of the setlist
    # for each remaining entry in the setlist, create a duplicate entry using the most recent version of the song from the same singer from the setlist date or before

    # keep track of which setlist files have been seen before

    songs_df = load_db()

    files = list(SETLISTS_DIR.glob(f"**/*"))
    # print("files")
    # print(files)
    files.sort()

    # TODO move to utils or somewhere else
    date_format = "%Y-%m-%d"

    for file in files:
        if file.name == 'Setlists.md' or file.is_dir():
            continue
        # print("File_IN")
        # print(file)

        res = False

        album_song_count = 0

        dates = []
        album_names = []
        with open(file) as f:
            lines = f.readlines()
        for line in lines:
            # print(line)
            if line.startswith('!!'):
                continue
            fields = [f.strip() for f in line.split('|')]
            if re.search(date_regex, fields[0]) and len(fields):
                date = parse(fields[0], fuzzy=True).strftime(date_format)
                if len(fields) > 1:
                    singer = fields[1]
                dates.append(date)
                if len(fields) >= 3:
                    album_names.append(fields[2])
                else:
                    album_names.append(f"{singer} {date} Karaoke")
            # TODO figure out what I intended to do with the above code, album_names isn't used anywhere
            elif re.search(r'\d+', fields[0]):
                album_song_count += 1


        # print("if not date in dates_df.get_column(\"Date\"):")
        # print(dates)
        # if not date in dates_df.get_column("Date"):
        #     # TODO log f"date from filename {date} is already in dates table"
        #     continue
        # TODO remove this commented out code so songs can be added to albums at later dates
        # print("File_IN")
        # print(file)
        albums = parse_setlist(file)

        if albums is None:
            continue
        
        for album, songs in albums.items():
            contains_new_songs: bool = False
            for date in dates:
                filtered_songs = songs_df.filter(pl.col('Album') == album)
                if filtered_songs.height:
                    existing_song_count = filtered_songs.height
                else:
                    existing_song_count = 0
                if existing_song_count and (len(albums[album]) == existing_song_count):
                    # TODO filter out songs already in database, and only add setlist entries for songs not in database
                    continue
                # print("fill_in_duplicates")
                # print(out.keys())
                # print("album: " + album)
                # print("date: " + date)
                # print(songs)
                contains_new_songs = False
                for song in songs:
                    contains_new_songs = contains_new_songs or not song['duplicate']
                if not contains_new_songs:
                    out[album] = albums[album][existing_song_count:]
                if album not in out.keys():
                    out[album] = []

            found_ids = []

            # TODO if song is discovered that goes in the middle of a setlist, will need to update track numbering of all songs after it
            # TODO if a gap exists in track numbering of an album in the database, only add songs in the gap to json

            # TODO fix for songs from one named setlist on a date getting added to a different named setlist for the same date

            def move_songs_to_named_album(src_album_name: str):
                # moves matching songs from out[src_album_name] to out[album]
                if src_album_name in out.keys():
                    songs_to_check = out[src_album_name]
                    for song in reversed(songs_to_check):
                        for entry in albums[album][existing_song_count:]:
                            # print()
                            # print(song)
                            # print(entry)
                            dup_encore_File_IN_check = (neutils.does_matching_song_exist_in_list(song, albums[album]) > neutils.does_matching_song_exist_in_list(song, out[album])) and not entry['duplicate'] and 'File_IN' in song.keys()
                            if neutils.do_songs_match(song, entry) and dup_encore_File_IN_check:
                                if album not in out.keys():
                                    out[album] = []
                                # print(album)
                                # print(src_album_name)
                                out[album].append(song)
                                out[src_album_name].remove(song)

            for date in dates:
                # print(date)
                move_songs_to_named_album(date)
            move_songs_to_named_album('custom')

            if contains_new_songs and album in out.keys():
                for song in out[album]:
                    for entry in albums[album][existing_song_count:]:
                        if (
                            (
                                neutils.get_song_artists_match_count(song['Artist'], entry['Artist'])
                             or neutils.get_song_artists_match_count(song['ArtistOG'], entry['Artist'])
                             or neutils.get_song_artists_match_count(song['Artist'], entry['ArtistOG'])
                             or neutils.get_song_artists_match_count(song['ArtistOG'], entry['ArtistOG'])
                            )
                            and
                            (
                                neutils.do_song_titles_match(song['Title'] + (( ' ' + song['Identify']) if (song['Identify'] is not None) and (not song['Identify'] == 'None') else ''),
                                                             entry['Title'] + (( ' ' + entry['Identify']) if (entry['Identify'] is not None) and (not entry['Identify'] == 'None') else ''))
                             or neutils.do_song_titles_match(entry['Title'] + (( ' ' + entry['Identify']) if (entry['Identify'] is not None) and (not entry['Identify'] == 'None') else ''),
                                                             song['Title'] + (( ' ' + song['Identify']) if (song['Identify'] is not None) and (not song['Identify'] == 'None') else ''))
                            )
                            and
                                song['Cover Artist'].lower() == entry['Cover Artist'].lower() and not entry['encore']):
                            for key in entry.keys():
                                if key not in song.keys():
                                    song[key] = entry[key]
                            song['id'] = entry['id']
                            song['Lead Singer'] = entry['Lead Singer']
                            found_ids.append(entry["id"])
                            # print(entry)
                            # print(song)
                            # print("")
                            # print("")


                # print("found_ids")
                # print(found_ids)

                out[album].sort(key=song_entry_sort_by_id)

                for entry in albums[album][existing_song_count:]:
                    # print(out)
                    # print("")
                    # print(entry)
                    # print("")
                    # print(found_ids)
                    # print("")
                    # print(entry['id'])
                    if entry["id"] not in found_ids:
                        out[album].insert((entry["id"]-1), entry)
                        # print('if entry["id"] not in found_ids:')
                    else:
                        # print(entry['id'] - 1)
                        # print(out[album][entry['id'] - 1 ])
                        # print(entry)
                        # print(out[album][entry['id'] - 1 ]['Date'])
                        # print(entry['Date'])
                        if res:
                            # print("res: True")
                            out[album][entry['id'] - 1 ]['Date'] = entry['Date']
                        # else:
                            # print("res: False")
                        # print(out[album][entry['id'] - 1 ]['Date'])
                        
                        out[album][entry['id'] - 1 - existing_song_count]['id'] = entry['id']
                        if entry['Image'] is not None:
                            out[album][entry['id'] - 1 - existing_song_count]['Image'] = entry['Image']
                        else:
                            out[album][entry['id'] - 1 - existing_song_count]['Image'] = ''

                        if entry['additional flags'] is not None:
                            out[album][entry['id'] - 1 - existing_song_count]['additional flags'] = entry['additional flags']
                        else:
                            out[album][entry['id'] - 1 - existing_song_count]['additional flags'] = ''



                    # print("print(out[album][entry['id'] - 1 ])")
                    # print(out[album][entry['id'] - 1 ])

    return out

def extract_all() -> neutils.SongJSON:
    """Runs all the extraction functions on all defined patterns.

    Returns:
        SongJSON: Output dictionary containg all files that are not yet in the database.\
            They are grouped by date, or category if no date was provided in filename.
    """
    songs_db = load_db()
    files = get_files(songs_db)
    regex = get_regexes()

    # for file in files:
    #     print(file)
    #     for song in files[file]:
    #         print(f"  {song}")
    # exit()

    out: neutils.SongJSON = {}

    # Official Releases
    extract_official(files['Official'], out)

    # Custom
    # print(files['Custom'])
    extract_custom(files["Custom"], out)

    # unofficial v3
    extract_unofficialV3(files["UnofficialV3"], out)

    # ARG songs
    extract_arg(files["ARG"], out)

    # fill in duplicates
    fill_in_setlists(out)

    # if 'custom' in out.keys() and len(out["custom"]) == 0:
    #     out.pop("custom")

    return out


def export_json(all_songs: neutils.SongJSON) -> None:
    """Takes an existing result of new files search and exports it in a json file.

    Args:
        all_songs (SongJSON): Dictionary with lists of files grouped by date.
    """

    # print("")
    # print(all_songs)
    all_keys = sorted(all_songs)
    # print("")
    # print(all_keys)

    for key in reversed(all_keys):
        if len(all_songs[key]) == 0:
            all_songs.pop(key)
            all_keys.remove(key)
    
    # print("")
    for key, songs in all_songs.items():
        # print(key)
        if not key == 'custom':
            for song in songs:
                # print(song)
                assert 'Date' in song.keys()

    keys_to_exclude = ['custom']
    # print(keys_to_exclude)
    dated_songs = {k:v for k,v in all_songs.items() if k not in keys_to_exclude}

    # Sorting songs by date for easier treatment
    # print(dated_songs)
    assert 'custom' not in dated_songs.keys()
    sorted_songs = dict(sorted(dated_songs.items(), key=lambda item: item[1][-1]['Date']))

    for key in keys_to_exclude:
        if key in all_songs.keys():
            sorted_songs[key] = all_songs[key]

    with open(SONGS_JSON, "w") as f:
        # print(sorted_songs)
        json.dump(sorted_songs, f, indent=2, ensure_ascii=False)
        f.write("\n")
