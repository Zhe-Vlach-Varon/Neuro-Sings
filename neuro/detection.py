"""Detects new files and parse their data."""

import json
import re
from datetime import datetime
from dateutil.parser import parse
from pathlib import Path
import tinytag

import polars as pl
from loguru import logger

from neuro import CUSTOM_DIR, ROOT_DIR, SONGS_JSON, UNOFFICIALV3_DIR, UNOFFV3_EXTRA, UNOFFV3_DISC66, OFFICIAL_RELEASE_DIR, COPYRIGHT_ISSUES_DIR, SETLISTS_DIR, OFFICIAL_CSV, ORIGINAL_CSV
from neuro.polars_utils import load_db
import neuro.utils as neutils

song_line_regex = r'^\d{1,} *\|'

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

    def get_audios(p: Path, *, filetype: str = "mp3", exclude_dirs = []) -> list[Path]:
        files = list(p.glob(f"**/*.{filetype}"))
        files_without_existing = list(filter(lambda f: f not in existing, files))
        filtered_files = [f for f in files_without_existing if not any(d in f.parts for d in exclude_dirs)]
        if len(files) == 0:
            logger.warning(f"no files found in {p} of filetype {filetype}")
        return filtered_files

    custom_dir = CUSTOM_DIR
    unofficialV3_dir = UNOFFICIALV3_DIR
    arg_dir = UNOFFICIALV3_DIR / UNOFFV3_EXTRA / UNOFFV3_DISC66
    official_dir = OFFICIAL_RELEASE_DIR
    copyright_issues_dir = COPYRIGHT_ISSUES_DIR

    return {
        "Custom": get_audios(custom_dir) + get_audios(custom_dir, filetype="flac"),
        "UnofficialV3": get_audios(unofficialV3_dir, exclude_dirs=[UNOFFV3_EXTRA]),
        "ARG": get_audios(arg_dir),
        "Official": list(official_dir.glob(f"*/**/*.mp3")), # search in all subdirectories recursively, can't use this glob pattern for UnofficialV3 as that would also get the ARG songs a second time
        "Copyright": get_audios(copyright_issues_dir),
    }


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
    for file in files:
        filename = file.stem
        fields = filename.split(' - ')
        artist = fields[0]
        title = fields[1]
        cover_artist = fields[2] if len(fields) > 2 else ""
        album = fields[3] if len(fields) > 3 else ""
        
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
            # 'Date': "2022-12-19",
            'Version': "1",
            'Special': "1",
            'Comment': None,
            'Hash_IN': neutils.get_audio_hash(Path(file)),
        }

        if album in out.keys():
            out[album].append(data)
        else:
            out[album] = [data]


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
            assert len(trackInfo.other['comment'])
            for comment in trackInfo.other['comment']:
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
        special = trackJSon['Special']
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
            'encore' : False,
            'Date' : date,
            'Lead Singer': cover_artist,
            'additional flags': "",
            'Version': version,
            'Hash_IN': neutils.get_audio_hash(Path(file)),
            'Special': special,
            'Comment': trackJSon['Comment'],
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
            'Special': '1',
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

    id = 1

    for song in official_songs_csv:
        for file in files:
            if str(file) in songs_db['File_IN']:
                continue
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
                    logger.error(f"how did we get here: neuro/detection.py: unexpected Cover Artist")
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
                    'Special': '1',
                    'Hash_IN': neutils.get_audio_hash(Path(file)),
                    'duplicate': False,
                    'encore': False,
                    'Comment': ''
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
                    'Special': '1',
                    'Hash_IN': neutils.get_audio_hash(Path(file)),
                    'duplicate': False,
                    'encore': False,
                    'Comment': ''
                    }
                if 'custom' in out.keys():
                    out['custom'].append(data)
                else:
                    out['custom'] = [data]
                id += 1

    return out

def get_default_album_name(album_song_count: int, singer:str, date: str) -> str:
    if album_song_count < 15:
        album = f"{singer} {date} Mini-Karaoke"
    else:
        album = f"{singer} {date} Karaoke"

    return album

def parse_setlist(p: Path) -> tuple[neutils.SongJSON, list[str]]:
    with open(p, 'r') as file:
        lines = file.readlines()

    logger.info(f'parsing setlist {p.name}')

    songs: neutils.SongJSON = {}


    is_singer_change_line = False
    is_song_line = False

    found_album_line = False
    album = ''

    lead_singer = "Neuro"
    album_art = None

    album_song_count = 0

    seen_songs = []
    dates = []

    for line in lines:
        if re.match(song_line_regex, line) is not None:
            album_song_count += 1

    for line in lines:
        if line.startswith('!!'):
            continue # this is a comment line, do not process
        fields = line.strip('\n').split('|')
        fields = [f.strip() for f in fields]

        date_format = "%Y-%m-%d"
        try:
            is_album_info_line = bool(datetime.strptime(fields[0], date_format))
        except:
            is_album_info_line = False


        # checking if starts with "Neuro" because 2026-04-01 April Fools karaoke included a song using v1 voice
        if not is_album_info_line and (fields[0].startswith("Neuro") or fields[0] == "Evil"):
            is_singer_change_line = True
        else:
            is_singer_change_line = False

        if (not is_album_info_line) and (not is_singer_change_line):
            is_song_line = True
        else:
            is_song_line = False

        
        if is_album_info_line:
            input_date = parse(fields[0])
            date = input_date.strftime(date_format)
            if len(fields) == 1:
                if found_album_line == False:
                    logger.error(f'first album info line only has date field: {p}')
                    exit(1)
                else:
                    continue
            else:
                album_art = None # reset album cover art to None
                singer = fields[1]
                lead_singer = singer
                if len(fields) < 2:
                    logger.error("not enough fields in album info line in setlist file: " + str(p))
                    exit(1)
                if len(fields) == 2:
                    album = get_default_album_name(album_song_count, singer, date)
                elif len(fields) >= 3 and not fields[2] == '':
                    album = fields[2]
                else:
                    album = get_default_album_name(album_song_count, singer, date)
                if album not in songs.keys():
                    songs[album] = []
                if len(fields) >= 4:
                    album_art = fields[3]
                found_album_line = True
                continue
        
        if is_singer_change_line and found_album_line:
            lead_singer = fields[0]
            continue

        if is_song_line and found_album_line:
            song_art = None # reset song specific art to None
            id = int(fields[0])
            song_title, identify = neutils.split_title_and_identify(fields[1])
            artist = fields[2]
            if not fields[3] == '':
                cover_artist = fields[3]
            else:
                cover_artist = lead_singer
            dupe = False
            encore = False
            
            if len(fields) >= 5 and not fields[4] == '':
                song_art = fields[4]
            else:
                song_art = album_art

            if len(fields) >= 6:
                additionalFlags = fields[5]
            else:
                additionalFlags = ''

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
                'id': id, # TODO unify Album_ID and id to instead be labeled Track_No or something to avoid confusion with database entry id
                'duplicate': dupe,
                'encore': encore,
                'additional flags': additionalFlags,
                'Version': None,
                'Comment': None,
                'Special': None,
            }

            dates.append(date)

            if neutils.does_matching_song_exist_in_list(data, seen_songs):
                data['encore'] = True
                data['duplicate'] = True

            songs[album].append(data)
            seen_songs.append(data)

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

    return songs, dates


def song_entry_sort_by_id(e):
    if e['id'] is None:
        return 999999
    return e['id']

def get_setlist_files() -> list[Path]:
    files = list(SETLISTS_DIR.glob(f"**/*"))
    karaoke_setlists = [f for f in files if 'non-karaoke' not in f.parts and not f.is_dir()]
    non_karaoke_setlists = [f for f in files if 'non-karaoke' in f.parts and not f.is_dir()]
    karaoke_setlists.sort()
    sorted_setlist_files = karaoke_setlists + non_karaoke_setlists

    return sorted_setlist_files


def fill_in_setlists(out: neutils.SongJSON | None = None) -> neutils.SongJSON:
    """Fills in missing setlist entries into the output dictionary."""
    if out is None:
        out = {}
    songs_df = load_db()

    sorted_setlist_files = get_setlist_files()
    total_setlist_song_count = 0

    def _move_songs_to_named_album(src_album_name: str, target_album: str, setlist_songs: list, existing_count: int) -> None:
        if src_album_name not in out:
            return
        songs_to_check = out[src_album_name]
        for entry in setlist_songs[existing_count:]:
            for i, song in enumerate(songs_to_check):
                if 'File_IN' in entry or entry['Date'] != song['Date']:
                    continue
                if neutils.do_songs_match(song, entry) and song['Date'] == entry['Date']:
                    if target_album not in out:
                        out[target_album] = []
                    out[src_album_name].pop(i)
                    song['id'] = entry['id']
                    song['Lead Singer'] = entry['Lead Singer']
                    song['Image'] = entry['Image']
                    song['additional flags'] = entry['additional flags']
                    if song['Date'] == entry['Date']:
                        setlist_songs.remove(entry)
                    out[target_album].append(song)
                    break

    def _merge_setlist_data_to_out(album: str, setlist_songs: list, existing_count: int, found_ids: list) -> None:
        for song in out[album]:
            for entry in setlist_songs[existing_count:]:
                title_match = (
                    neutils.do_song_titles_match(
                        song['Title'] + ((' ' + song['Identify']) if song.get('Identify') and song['Identify'] != 'None' else ''),
                        entry['Title'] + ((' ' + entry['Identify']) if entry.get('Identify') and entry['Identify'] != 'None' else '')
                    ) or neutils.do_song_titles_match(
                        entry['Title'] + ((' ' + entry['Identify']) if entry.get('Identify') and entry['Identify'] != 'None' else ''),
                        song['Title'] + ((' ' + song['Identify']) if song.get('Identify') and song['Identify'] != 'None' else '')
                    )
                )

                artist_match = (
                    neutils.get_song_artists_match_count(song['Artist'], entry['Artist']) > 0 or
                    neutils.get_song_artists_match_count(song['ArtistOG'], entry['Artist']) > 0 or
                    neutils.get_song_artists_match_count(song['Artist'], entry['ArtistOG']) > 0 or
                    neutils.get_song_artists_match_count(song['ArtistOG'], entry['ArtistOG']) > 0
                )

                cover_match = song['Cover Artist'].lower() == entry['Cover Artist'].lower() and not entry['encore']
                date_match = ('Date' in song and 'Date' in entry and song['Date'] == entry['Date']) or ('Date' not in song)

                if artist_match and title_match and cover_match and date_match:
                    for key in entry.keys():
                        if key not in song:
                            song[key] = entry[key]
                    song['id'] = entry['id']
                    song['Lead Singer'] = entry['Lead Singer']
                    found_ids.append(entry["id"])
                    break

    def _sort_and_insert_songs(album: str, setlist_songs: list, existing_count: int, found_ids: list) -> None:
        out[album].sort(key=song_entry_sort_by_id)

        for entry in setlist_songs:
            if entry["id"] not in found_ids or len(out[album]) < entry["id"]:
                out[album].insert(entry["id"] - 1, entry)
            else:
                idx = entry['id'] - 1 - existing_count
                out[album][idx]['id'] = entry['id']
                out[album][idx]['Image'] = entry['Image'] if entry['Image'] is not None else ''
                out[album][idx]['additional flags'] = entry['additional flags'] if entry['additional flags'] is not None else ''

    for file in sorted_setlist_files:
        if file.name == 'Setlists.md' or file.is_dir():
            continue

        albums, dates = parse_setlist(file)
        if not albums:
            continue

        for album, songs in albums.items():
            total_setlist_song_count += len(songs)

            filtered_songs = songs_df.filter(pl.col('Album') == album)
            existing_song_count = filtered_songs.height if filtered_songs.height else 0

            if existing_song_count and len(songs) == existing_song_count:
                continue

            contains_new_songs = any(not song['duplicate'] for song in songs)

            if not contains_new_songs:
                out[album] = albums[album][existing_song_count:]
                continue

            if album not in out:
                out[album] = []

            found_ids = []
            for src_album_name in dates + ['custom']:
                _move_songs_to_named_album(src_album_name, album, songs, existing_song_count)

            if contains_new_songs and album in out:
                _merge_setlist_data_to_out(album, songs, existing_song_count, found_ids)

            _sort_and_insert_songs(album, songs, existing_song_count, found_ids)

    logger.info(f"total songs found in setlists: {total_setlist_song_count}")

    for album in list(out.keys()):
        filtered = songs_df.filter(pl.col('Album') == album)
        for song in reversed(out[album]):
            if 'File_IN' not in song:
                song['duplicate'] = True
            if neutils.does_matching_song_exist_in_list(song, filtered.to_dicts()):
                logger.info(f"removing {song['Artist']} - {song['Title']} - {song['Cover Artist']} with date {song['Date']}")
                out[album].remove(song)
        if not out[album]:
            del out[album]

    return out

def extract_all() -> neutils.SongJSON:
    """Runs all the extraction functions on all defined patterns.

    Returns:
        SongJSON: Output dictionary containg all files that are not yet in the database.\
            They are grouped by date, or category if no date was provided in filename.
    """
    songs_db = load_db()
    files = get_files(songs_db)

    out: neutils.SongJSON = {}

    # Official Releases
    extract_official(files['Official'], out)

    # Songs with copyright issues that can't be distributed
    extract_unofficialV3(files['Copyright'], out)

    # Custom
    extract_custom(files["Custom"], out)

    # unofficial v3
    extract_unofficialV3(files["UnofficialV3"], out)

    # ARG songs
    extract_arg(files["ARG"], out)

    # fill in duplicates
    fill_in_setlists(out)


    return out

def _is_twin_duet_stream(album_name: str, songs: list) -> bool:
    """Mirrors the `twin_duet_stream` detection in json_to_csv.update_db:
    an album is a twin duet stream when it is a karaoke album (i.e. not one of the
    non-karaoke setlist stems) and every song in it is covered by 'Neuro & Evil'."""
    if album_name in neutils.get_non_karaoke_album_names():
        return False
    return all(song['Cover Artist'] == 'Neuro & Evil' for song in songs)


def _expected_flags(song: dict, is_twin_duet_stream: bool = False) -> str:
    """Compute the flags a setlist song is expected to carry in the database,
    replicating the flag logic in json_to_csv.update_db:
        get_flags + copyright issue + additional flags,
        then the twin-duet stripping of the neuro/evil flags,
        then the 'Neuro & Evil' + 'original' duet handling.
    """
    flags = neutils.get_flags(song)
    if neutils.is_copyright_issue(song['Title'], song['Artist']):
        flags += 'copyright_issues;'
    flags += song['additional flags']

    if is_twin_duet_stream:
        flags = flags.replace('evil;', '').replace('neuro;', '')

    if song['Cover Artist'] == 'Neuro & Evil' and 'original' in flags:
        flags = flags.replace('neuro;', '').replace('evil;', '')
        if 'duet;' not in flags:
            flags += 'duet;'

    return flags


def _flag_set(flags: str | None) -> set:
    """Split a semicolon-separated flags string into a set of individual flags."""
    return {f for f in (flags or '').split(';') if f}


def check_missing_setlist_entries() -> list[dict]:
    """Checks the song database for the following cases:
            songs in setlist files not in database
            songs in database not in setlist files
            albums in database not in setlist files
            track number mismatches between album in database and album in setlist
            flag mismatches between the setlist-derived expectation and the database
        keeping in mind that setlists can contain multiple instances of a song with different track numbers :IMPORTANT: this is intended, as sometimes a song will be repeated as an encore and will thus be in the setlist multiple times with different track numbers

        builds a list of found discrepencies containing dicts of with the following fields:
            'Type': 'Missing'|'Extra'|'Mismatch'|'Flags'|'Album'    where Missing means track missing from DB, 'Extra' means unexpected track in DB, 'Mismatch' means track number mismatch between setlist and DB, 'Flags' means the DB flags differ from the setlist-derived expectation, and 'Album' means that this album exists in the database but not in any setlists
            'Source_Setlist': str|None                      the filepath of a setlist file, or none if only present in DB
            'Album': str
            'Date': str
            'Artist': str
            'Title': str
            'Identify': str
            'Cover Artist': str
            'Track_ID': int
        when 'Type' is 'Flags' also include 'Missing_Flags' and 'Extra_Flags' (lists)
        when 'Type' is 'Album' only include 'Type' and 'Album'

        logs found errors using the following format:
            if 'Missing', 'Extra', 'Mismatch', or 'Flags':
                issue-type: song info, setlist_file if not None
            if 'Album':
                issue-type: album name

        """
    songs_df = load_db()
    discrepencies = []
    
    sorted_setlist_files = get_setlist_files()

    total_setlist_song_count = 0
    setlist_albums = set()
    setlist_album_to_file_mapping = {}

    for file in sorted_setlist_files:
        if file.name == 'Setlists.md' or file.is_dir():
            continue
            
        albums, dates = parse_setlist(file)
        if not albums:
            continue
            
        for album_name, songs in albums.items():
            setlist_albums.add(album_name)
            setlist_album_to_file_mapping[album_name] = file

            total_setlist_song_count += len(songs)

            db_songs = songs_df.filter((pl.col('Album') == album_name)).to_dicts()

            db_tracks = [
                {
                    'Track_No': db_song['Album_ID'],
                    'Artist': db_song['Artist'],
                    'Title': db_song['Title'],
                    'Identify': db_song['Identify'],
                    'Cover Artist': db_song['Cover Artist'],
                    'Date': db_song['Date'],
                    'Album': db_song['Album'],
                    'Flags': db_song['Flags']
                } for db_song in db_songs]
            
            setlist_tracks = [
                {
                    'Track_No': sl_song['id'],
                    'Artist': sl_song['Artist'],
                    'Title': sl_song['Title'],
                    'Identify': sl_song['Identify'],
                    'Cover Artist': sl_song['Cover Artist'],
                    'Date': sl_song['Date'],
                    'Album': album_name
                } for sl_song in songs]
            
            matched_pairs = []  # List of (sl_track, db_track, raw_sl_song)
            unmatched_setlist = []
            unmatched_db = []

            # Match setlist tracks to DB tracks
            used_db_indices = set()
            for sl_idx, sl_track in enumerate(setlist_tracks):
                matched_idx = None
                for j, db_track in enumerate(db_tracks):
                    if j in used_db_indices:
                        continue
                    if neutils.do_songs_match(sl_track, db_track, ignore_date=True):
                        matched_idx = j
                        break

                if matched_idx is not None:
                    matched_pairs.append((sl_track, db_tracks[matched_idx], songs[sl_idx]))
                    used_db_indices.add(matched_idx)
                else:
                    unmatched_setlist.append(sl_track)

            # Collect unmatched DB tracks
            for j, db_track in enumerate(db_tracks):
                if j not in used_db_indices:
                    unmatched_db.append(db_track)

            # Check for track number mismatches and flag discrepancies among matched tracks
            is_twin_duet = _is_twin_duet_stream(album_name, songs)
            # 'duplicate'/'encore' are structural markers added to encore entries in
            # update_db; they are not part of the musical content flags, so ignore them
            structural = {'duplicate', 'encore'}

            for sl_track, db_track, raw_sl_song in matched_pairs:
                if sl_track['Track_No'] != db_track['Track_No']:
                    discrepencies.append({
                        'Type': 'Mismatch',
                        'Source_Setlist': str(file),
                        'Album': album_name,
                        'Date': sl_track['Date'],
                        'Artist': sl_track['Artist'],
                        'Title': sl_track['Title'],
                        'Identify': sl_track['Identify'],
                        'Cover Artist': sl_track['Cover Artist'],
                        'Setlist_ID': sl_track['Track_No'],
                        'DB_ID': db_track['Track_No'],
                    })

                # Verify the song's flags against the setlist-derived expectation
                expected_flags = _flag_set(_expected_flags(raw_sl_song, is_twin_duet)) - structural
                actual_flags = _flag_set(db_track['Flags']) - structural
                missing_flags = expected_flags - actual_flags
                extra_flags = actual_flags - expected_flags
                if missing_flags or extra_flags:
                    discrepencies.append({
                        'Type': 'Flags',
                        'Source_Setlist': str(file),
                        'Album': album_name,
                        'Date': sl_track['Date'],
                        'Artist': sl_track['Artist'],
                        'Title': sl_track['Title'],
                        'Identify': sl_track['Identify'],
                        'Cover Artist': sl_track['Cover Artist'],
                        'Track_ID': sl_track['Track_No'],
                        'Missing_Flags': sorted(missing_flags),
                        'Extra_Flags': sorted(extra_flags),
                    })

            # Add missing tracks (in setlist but not DB)
            for sl_track in unmatched_setlist:
                discrepencies.append({
                    'Type': 'Missing',
                    'Source_Setlist': str(file),
                    'Album': album_name,
                    'Date': sl_track['Date'],
                    'Artist': sl_track['Artist'],
                    'Title': sl_track['Title'],
                    'Identify': sl_track['Identify'],
                    'Cover Artist': sl_track['Cover Artist'],
                    'Track_ID': sl_track['Track_No'],
                })

            # Add extra tracks (in DB but not setlist)
            for db_track in unmatched_db:
                discrepencies.append({
                    'Type': 'Extra',
                    'Source_Setlist': None,
                    'Album': db_track['Album'],
                    'Date': db_track['Date'],
                    'Artist': db_track['Artist'],
                    'Title': db_track['Title'],
                    'Identify': db_track['Identify'],
                    'Cover Artist': db_track['Cover Artist'],
                    'Track_ID': db_track['Track_No'],
                })


    # Check for albums in DB without setlist
    db_albums = set(songs_df.get_column('Album').unique().to_list())
    missing_albums = db_albums - setlist_albums
    for album_name in missing_albums:
        discrepencies.append({
            'Type': 'Missing Setlist',
            'Album': album_name,
        })
                    
    if discrepencies:
        logger.warning(f"Found {len(discrepencies)} issues with setlist entries in the database.")
        for entry in discrepencies:
            if entry['Type'] == 'Missing':
                logger.warning(f"  Missing: {entry['Album']} ({entry['Date']}) - {entry['Track_ID']}. {entry['Artist']} - {entry['Title']} {entry['Identify']}")
            elif entry['Type'] == 'Mismatch':
                logger.warning(f"  Track Mismatch: {entry['Album']} ({entry['Date']}) - Setlist: {entry['Setlist_ID']}, DB: {entry['DB_ID']}. {entry['Artist']} - {entry['Title']}")
            elif entry['Type'] == 'Extra':
                logger.warning(f"  Extra in DB: {entry['Album']} ({entry['Date']}) - {entry['Track_ID']}. {entry['Artist']} - {entry['Title']}")
            elif entry['Type'] == 'Flags':
                logger.warning(f"  Flag Mismatch: {entry['Album']} ({entry['Date']}) - {entry['Track_ID']}. {entry['Artist']} - {entry['Title']}. Missing: {entry['Missing_Flags']}, Extra: {entry['Extra_Flags']}")
            elif entry['Type'] == 'Album':
                logger.warning(f"  Unexpected Album: {entry['Album']}")
            elif entry['Type'] == 'Missing Setlist':
                logger.warning(f"  Missing Setlist: {entry['Album']}")
    else:
        logger.info("All setlist entries match the database.")
        
    return discrepencies

def run_setlist_check() -> int:
    return len(check_missing_setlist_entries()) == 0

def export_json(all_songs: neutils.SongJSON) -> None:
    """Takes an existing result of new files search and exports it in a json file.

    Args:
        all_songs (SongJSON): Dictionary with lists of files grouped by date.
    """


    all_keys = sorted(all_songs)

    for key in reversed(all_keys):
        if len(all_songs[key]) == 0:
            all_songs.pop(key)
            all_keys.remove(key)
    
    for key, songs in all_songs.items():
        if not key == 'custom':
            for song in songs:
                assert 'Date' in song.keys()

    keys_to_exclude = ['custom']
    dated_songs = {k:v for k,v in all_songs.items() if k not in keys_to_exclude}

    # Sorting songs by date for easier treatment
    assert 'custom' not in dated_songs.keys()
    sorted_songs = dict(sorted(dated_songs.items(), key=lambda item: item[1][0]['Date']))


    with open(SONGS_JSON, "w") as f:
        # print(sorted_songs)
        json.dump(sorted_songs, f, indent=2, ensure_ascii=False)
        f.write("\n")
