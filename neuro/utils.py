"""Utility functions for the whole module"""

from __future__ import annotations

import os
import sys
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TextIO
import unicodedata
from typing import Optional

import xxhash

import hashlib
from mutagen.id3 import ID3, ID3NoHeaderError

import tinytag
import json
import csv

import loguru
from loguru import logger

from neuro import DATA_DIR, LOG_DIR, OFFICIAL_RELEASE_DIR, UNOFFICIALV3_DIR, CUSTOM_DIR, DRIVE_DIR, SETLISTS_DIR, UNOFFV3_EXTRA, UNOFFV3_DISC66

SongEntry = dict[str, Optional[str]]
"""Dictionary representing a song in the JSON, containing fields like "Title", "Artist", etc..."""
SongJSON = dict[str, list[SongEntry]]
"""Whole JSON file expected format. A list of date-indexed lists of songs."""

# It's ints to be easier to pass via CLI, instead of typing the level with a risk of typo
VERBOSE = {
    0: "CRITICAL",
    1: "ERROR",
    2: "WARNING",
    3: "SUCCESS",
    4: "INFO",
    5: "DEBUG",
    6: "TRACE",
}
"""Correspondance for levels of verbosity"""


def rotation_fn(_msg: loguru.Message, file_opened: TextIO) -> bool:
    """Rotation function for logfiles.

    Args:
        _msg (loguru.Message): Message.
        file_opened (TextIO): File object.

    Returns:
        bool: True (should change file) if file is more than a week old or bigger than 2MiB.
    """
    file = Path(file_opened.name)
    # File is more than 1 week old
    is_old = datetime.now().timestamp() - file.stat().st_ctime > 7 * 86400
    # File is >2MiB
    is_big = file.stat().st_size > (2 << 20)  # Multiplies by 1024 instead of 1000
    return is_old or is_big


def format_logger(*, log_file: Path = LOG_DIR / "neuro.log", verbosity: int = 5) -> None:
    """Formats a loguru logger, can be called from anywhere to set it up.

    Args:
        log_file (Path, optional): File to store the logs. Defaults to LOG_DIR/"neuro.log".
        verbosity (int, optional): Level of verbosity [0-6], the higher the more verbose, see VERBOSE\
            Variable in this file for more details. Defaults to 5 (DEBUG).

    Raises:
        ValueError: If verbosity isn't in [0,6].
    """

    if verbosity not in VERBOSE:
        logger.error(f"Logger got wrong verbosity {verbosity}")
        raise ValueError("Wrong Level of verbosity, expect int in [0,6]")

    level: str = VERBOSE[verbosity]
    # Adds the segment on multiple lines to disable each at will by commenting
    format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>"
    format += " | <level>{level:<8}</level>"
    format += " | <level>{message}</level>"

    # Function name is defined separately because it's only used in the logfile to avoid cluttered terminal
    f_name = " | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"

    # Resets all previously existing sinks
    logger.remove()

    # Log file
    logger.add(
        log_file,
        format=format + f_name,
        enqueue=True,
        level=level,
        rotation=rotation_fn,
    )
    logger.info(f"Launched program with command {' '.join(sys.argv)}")

    # Console log
    logger.add(sys.stderr, format=format, level=level, enqueue=True)


def file_check(file_: Path | str, /) -> None:
    """Checks if a given file exists or not.

    Args:
        file (Path | str): File to check (positional argument).

    Raises:
        FileNotFoundError: If the file doesn't exist.
    """
    file: Path = Path(file_)
    if not file.exists():
        err = f"File '{str(file)}' not found."
        logger.error(err)
        raise FileNotFoundError(err)


def time_format(dt: float, precise: bool = False) -> str:
    """Formats a floating point number of seconds as min/sec, sec, or ms, ...
    Done automatically once and for all

    Args:
        dt (float): Time
        precise (bool, optional): Display seconds if dt > 3600. Display decimals\
            if dt>60. Defaults to False.

    Returns:
        str: Pretty time string
    """
    i = int(dt)
    if dt > 3600:
        hour = i // 60
        min, sec = divmod(i, 60)
        extra = f"{sec}s" if precise else ""
        return f"{hour}h{min}mn" + extra
    if dt > 60:
        min, sec = divmod(i, 60)
        extra = f".{dt - i:.2f}" if precise else ""
        return f"{min}mn{sec}s" + extra
    elif dt > 1:
        return f"{dt:.2f}s"
    elif dt > 1e-3:
        return f"{dt * 1e3:.2f} ms"
    elif dt > 1e-6:
        return f"{dt * 1e6:.2f} μs"
    else:
        return f"{dt * 1e9:.2f} ns"


class MP3GainMode(Enum):
    """Possible settings for mp3gain. Contains both mode and type options, 2 types would\
        be too much boilerplate imo.
    """

    PER_PRESET = 0x0
    ON_ALL = 0x1
    OFF = 0xFF

    GAIN = 0x80
    TAG = 0x81


MP3ModeTuple = tuple[MP3GainMode, MP3GainMode]

# TODO update attribution and get link to one of Nyss's repos

# get_audio_hash function taken from Nyss
# MIT License

# Copyright (c) 2026 Nyss

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
def get_audio_hash(file_path: Path) -> (str | None):
    try:

        try:
            audio_tags = ID3(file_path)
            header_size = audio_tags.size  # Mutagen provides the full tag size including header
        except ID3NoHeaderError:
            header_size = 0

        logger.info(file_path.stat().st_size)
        file_size = file_path.stat().st_size
        if file_size < 3000:
            logger.error(f"{file_path.name} is too small!")
            return None

        with open(file_path, 'rb') as f:
            file_data = f.read()

            footer_size = 0
            f.seek(-128, 2) # Seek 128 bytes from the end (2)
            if f.read(3) == b'TAG':
                footer_size = 128
            

            if (file_size - footer_size - 1_000_000) > 987: # check to prevent negative indexes
                end_index = file_size - footer_size - 1_000_000 ### about a Mb offset for the audio

            else:
                end_index = int((file_size - footer_size - header_size) * 3 / 4 + header_size)

            logger.info(f"End Index: {end_index}")

            start_index = end_index - 987 ### reads a 987 bytes for the hash

            raw_audio = file_data[start_index:end_index]

        # 4. Hash the raw audio
        return xxhash.xxh64(raw_audio).hexdigest()

    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return None

def get_audio_hash_to_file_mapping(p: Path, *, filetype: str = "mp3") -> dict:
    files = list(p.glob(f"**/*.{filetype}"))
    file_mapping = {}

    for file in files:
        hash = get_audio_hash(file)
        file_mapping[hash] = Path(file)
    
    return file_mapping

def do_song_titles_match(existing_song_title: str, new_song_title: str) -> bool:
    if existing_song_title is None or new_song_title is None:
        return False

    if existing_song_title.startswith('Numbers') and new_song_title.startswith('Numbers'):
        if existing_song_title == 'Numbers' and new_song_title == 'Numbers':
            return True
        elif existing_song_title == 'Numbers II' and new_song_title == 'Numbers II':
            return True
        elif existing_song_title == 'Numbers III' and new_song_title == 'Numbers III':
            return True
        else:
            return False

    songTitleNonAlphaNumStripRegex = r'[^a-z0-9\/&]'

    new_title = re.sub(songTitleNonAlphaNumStripRegex, '', str(remove_accents(new_song_title)).lower())
    existing_title = re.sub(songTitleNonAlphaNumStripRegex, '', str(remove_accents(existing_song_title)).lower())
    nightcore_regex = r'((nightcore|chipmunk)(ver(sion)?)?)'

    new_is_nightcore = False
    existing_is_nightcore = False

    if re.search(nightcore_regex, new_title):
        new_is_nightcore = True
        new_title = re.sub(nightcore_regex, '', new_title)

    if re.search(nightcore_regex, existing_title):
        existing_is_nightcore = True
        existing_title = re.sub(nightcore_regex, '', existing_title)

    titles_match = (str.lower(new_title) in str.lower(existing_title)) and (new_is_nightcore == existing_is_nightcore)

    return titles_match

def get_song_artists_match_count(existing_song_artists: str, new_song_artists: str) -> int:
    artistCharacterStripRegex = r'[\_\-\(\)\[\]\{\}\<\>\.\*\/\'\\]'
    artistStripProducerPRegex = r'p$'
    artistNameSplitRegex = r',|&|\+|( [xX] )'

    existing_artists = re.split(artistNameSplitRegex,  str(re.sub(artistStripProducerPRegex, '', re.sub(artistCharacterStripRegex, '', str(remove_accents(existing_song_artists))).lower())))
    new_artists = re.split(artistNameSplitRegex,  str(re.sub(artistStripProducerPRegex, '', re.sub(artistCharacterStripRegex, '', str(remove_accents(new_song_artists))).lower())))

    artists_match_count = 0

    for existing_artist in existing_artists:
        for new_artist in new_artists:
            if re.sub(' ', '', str(new_artist)) in re.sub(' ', '', str(existing_artist)):
                artists_match_count += 1

    return artists_match_count

def remove_accents(s):
   return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

english_title_translation_regex = r'\(.*?\)'
# TODO load from file
title_ascii_special_negative_cases = [
    'da ba dee',
    'gotta catch em all',
    'me',
    'you',
    'ski-ba-bop-ba-dop-bop',
    '2023', '2024', '2025',
    'what about us',
    'i believe in you',
    '500 miles',
    'o',
    'number one victory royale',
    'ive had',
    'dont fear',
    'out your eyes then drown you to death',
    'what youve given me',
]

def split_title_and_identify(title_and_identify: str):
    title_identify_regex = r'^(?P<title>.*) \((?P<identify>.*)\)$'
    matched = re.match(title_identify_regex, title_and_identify)
    if matched is None:
        title = title_and_identify
        identify = "None"
    elif replace_non_ascii_chars(remove_accents(matched.group('identify'))).lower() not in title_ascii_special_negative_cases:
        title = matched.group('title')
        identify = matched.group('identify')
    else:
        title = title_and_identify
        identify = "None"


    return title, identify

# TODO move special cases into separate files

title_ascii_special_replace_cases = {
    '/ / // / /': 'Slash Slash Slash',
    'S!CK': 'SICK',
    'デビルじゃないもん ((Not) A Devil)': '(Not) A Devil',
    '真夜中のドア〜Stay With Me': 'Stay With Me',
    '学猫叫 (Xue Miao Jiao)': 'Xue Miao Jiao (Learn To Meow)',
    '炜WARD ROMANCE': 'WEIWARD ROMANCE',
    '4nim0sity(99.999999999%)': '4nim0sity',
    'ニア (Near) (Birthday ver.)': 'Near (Birthday ver.)'
}

ascii_character_replacement_mapping = {
    '’': '\'',
    '＊': '*',
    '★': ' ',
    '  ': ' ',
    ';': '',
}

non_ascii_char_regex = r'[^a-zA-Z0-9\-\,\. ]'

def replace_non_ascii_chars(s: str) -> str:

    for key in ascii_character_replacement_mapping.keys():
        s = s.replace(key, ascii_character_replacement_mapping[key])
    s = re.sub(non_ascii_char_regex, '', s)
    return s

def extract_english_title_translation(title: str) -> (str | None):
    if title in title_ascii_special_replace_cases.keys():
        return title_ascii_special_replace_cases[title]

    title_ascii_search_result = re.search(english_title_translation_regex, title)
    if title_ascii_search_result is not None:
        title_ascii = str(title_ascii_search_result.group())[1:-1]
        title_ascii = replace_non_ascii_chars(remove_accents(title_ascii))
        if title_ascii.lower() in title_ascii_special_negative_cases:
            title_ascii = None
    else:
        title_ascii = None

    if title == 'Secret Base 君がくれたもの (Kimi ga Kureta Mono)':
        title_ascii = 'Secret Base Kimi ga Kureta Mono'

    return title_ascii

# TODO load from file
artist_ascii_special_cases_mapping = {
    "μ's": "muse",
    "DECO*27": "DECO 27",
    "K/DA": "KDA",
}

def get_artist_ascii(artist: str) -> str:
    for key in artist_ascii_special_cases_mapping:
        artist = artist.replace(key, artist_ascii_special_cases_mapping[key])

    return replace_non_ascii_chars(remove_accents(artist))

def do_songs_match(s1: SongEntry, s2: SongEntry, ignore_date: bool = False) -> bool:
    
    artists_match = get_song_artists_match_count(s1['Artist'], s2['Artist']) > 0 or get_song_artists_match_count(s2['Artist'], s1['Artist']) > 0
    titles_match = do_song_titles_match(s1['Title'], s2['Title']) or do_song_titles_match(s2['Title'], s1['Title'])
    identifys_match = do_song_titles_match(s1['Identify'], s2['Identify']) or do_song_titles_match(s2['Identify'], s1['Identify'])
    dates_match = ('Date' not in s2.keys() or s1['Date'] == s2['Date']) or ignore_date
    cover_artists_match = s1['Cover Artist'] == s2['Cover Artist']
    final_result = artists_match and titles_match and dates_match and cover_artists_match and identifys_match


    return final_result

def get_matching_songs_from_list(song: SongEntry, lst: list[SongEntry], ignore_dates: bool = False):
    matches = []
    for entry in lst:
        if do_songs_match(song, entry, ignore_dates):
            matches.append(entry)
    return matches

def does_matching_song_exist_in_list(song: SongEntry, lst: list[SongEntry], ignore_dates: bool = False) -> int:
    """returns count of matching songs in list"""
    match_count = 0
    for entry in lst:
        if do_songs_match(song, entry, ignore_dates):
            match_count += 1
    return match_count

non_karaoke_albums = []

def get_non_karaoke_album_names() -> list:
    if not len(non_karaoke_albums):
        setlists = list(SETLISTS_DIR.glob(f"**/*"))
        for setlist in setlists:
            if setlist.name == 'Setlists.md' or setlist.is_dir():
                continue
            if setlist.is_relative_to(SETLISTS_DIR / 'v3 voice' / 'non-karaoke'):
                non_karaoke_albums.append(setlist.stem)
    return non_karaoke_albums


def sanitize_filename(filename: str) -> str:
    FORBIDDEN_CHARS = {
        '\\': ' backslash ',
        '/': ' slash ',
        ':': ' ', 
        '*': '_', 
        '?': ' ',
        '"': "'",
        '<': '[',
        '>': ']',
        '|': '_'
    }

    for char in FORBIDDEN_CHARS:
        filename = filename.replace(char, FORBIDDEN_CHARS[char])

    while("  " in filename):
        filename = filename.replace("  ", " ")

    ## some kanji were getting divided into two symbols: ヴ -> ウ  ゙
    filename = unicodedata.normalize('NFC', filename)

    return filename

_copyright_entries = []

def _load_copyright_entries() -> list:
    """Load and cache copyright_issues.csv entries (loaded once per process)."""
    if not _copyright_entries:
        copyright_file = DATA_DIR / "copyright_issues.csv"
        if copyright_file.exists():
            with open(copyright_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='|')
                for row in reader:
                    _copyright_entries.append({
                        'title': row.get('title', '').strip(),
                        'artist': row.get('artist', '').strip(),
                    })
    return _copyright_entries

def is_copyright_issue(title: Optional[str], artist: Optional[str]) -> bool:
    """Checks if a song matches any entry in copyright_issues.csv.

    Uses do_song_titles_match and get_song_artists_match_count for matching.

    Args:
        title: Song title to check.
        artist: Song artist to check.

    Returns:
        bool: True if the song matches any copyright issue entry.
    """
    if title is None or artist is None:
        return False

    copyright_entries = _load_copyright_entries()

    for entry in copyright_entries:
        title_match = do_song_titles_match(title, entry['title'])
        artist_match = get_song_artists_match_count(artist, entry['artist']) > 0
        if title_match and artist_match:
            return True

    return False

def get_flags(song: SongEntry) -> str:

    """ Singing voice version: 'v1', 'v2', 'v3', ''
        Lead singer: 'neuro', 'evil'
        Duet: 'duet', ''
        Duplicate: 'duplicate', ''
        Encore: 'encore', ''
        Collab: 'collab', ''
        Official: 'official', ''
        Original: 'original', ''
        Halloween: 'halloween', ''
            manually added flag
        Christmas: 'christmas', ''
            manually added flag
        Quarantine: 'quarantine', ''
            manually added flag
        Mashup: 'mashup', ''
        ARG: 'arg', ''
        arg songs have only the arg flag"""

    flags: str = ""

    cover_artist = song['Cover Artist']
    lead_singer = song['Lead Singer']
    duplicate = song['duplicate']
    encore = song['encore']

    if lead_singer == 'Study-sama':
        return 'arg;'

    if '[v1]' in cover_artist:
        flags = 'v1;neuro;'
    elif '[v2]' in cover_artist:
        flags = 'v2;neuro;'
    else:
        flags = 'v3;'

        if lead_singer == 'Neuro':
            flags += 'neuro;'
        if lead_singer == 'Evil':
            flags += 'evil;'
    if cover_artist == 'Neuro & Evil':
        flags += 'duet;'
    elif ('Neuro ' in cover_artist and ' & ' in cover_artist and 'Evil' not in cover_artist) or 'Evil & ' in cover_artist or 'Neuro, Evil, ' in cover_artist:
        flags += 'collab;'

    if song['Cover Artist'] == 'Neuro & Evil' and 'original' in flags:
        flags = flags.replace('neuro;', '').replace('evil;', '')
        if 'duet;' not in flags:
            flags += 'duet;'
    
    return flags