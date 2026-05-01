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

import loguru
from loguru import logger

from neuro import LOG_DIR, OFFICIAL_RELEASE_DIR, UNOFFICIALV3_DIR, CUSTOM_DIR, DRIVE_DIR, SETLISTS_DIR

SongEntry = dict[str, Optional[str]]
"""Dictionary representing a song in the JSON, containing fields like "Song", "Artist", etc..."""
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


def get_sha256(file: Path) -> str:
    """Computes the SHA-256 of a given file.

    Args:
        file (Path): File to get the hash.

    Returns:
        str: A string with the hash.
    """
    # https://stackoverflow.com/questions/22058048/hashing-a-file-in-python
    # BUF_SIZE is totally arbitrary, change for your app!
    BUF_SIZE = 65536  # lets read stuff in 64kb chunks!

    sha256 = hashlib.sha256()
    file_check(file)
    with open(file, "rb") as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()

    


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
    # print(p)
    files = list(p.glob(f"**/*.{filetype}"))
    file_mapping = {}

    for file in files:
        # print(file)
        hash = get_audio_hash(file)
        file_mapping[hash] = Path(file)
    
    return file_mapping

def get_old_to_new_file_mapping_by_audio_hash(old_dir: Path, new_dir: Path, filetype: str = "mp3") -> dict:
    old_to_new_mapping: dict = {}

    old_file_map = get_audio_hash_to_file_mapping(old_dir)
    new_file_map = get_audio_hash_to_file_mapping(new_dir)

    old_hashes = list(dict.fromkeys(old_file_map.keys()))
    new_hashes = list(dict.fromkeys(new_file_map.keys()))

    in_both_count = 0
    in_new_only_count = 0
    in_old_only_count = 0

    in_old_only_list = []
    in_new_only_list = []
    in_both_list = []

    for hash in old_hashes:
        # print("")
        # print(hash)
        # print(old_file_map[hash])
        if hash in new_hashes:
            # print(new_file_map[hash])
            in_both_count += 1
            in_both_list.append((hash, old_file_map[hash], new_file_map[hash]))
        else:
            # print("not in new")
            in_old_only_count += 1
            in_old_only_list.append((hash, old_file_map[hash], "N/A"))
    
    for hash in new_hashes:
        # print("")
        # print(hash)
        # print(new_file_map[hash])
        # if hash in old_hashes:
        if not hash in old_hashes:
            # print(old_file_map[hash])
        # else:
            # print("not in old")
            in_new_only_count += 1
            in_new_only_list.append((hash, "N/A", new_file_map[hash]))

    # print("counts")
    # print("in both: " + str(in_both_count))
    # print("in new only: " + str(in_new_only_count))
    # print("in old only: " + str(in_old_only_count))

    # print("\n\n")

    # print("In new archive only")
    # for song in in_new_only_list:
        # print(song)
    
    # print("\n\n")

    # print("In old archive only:")
    # for song in in_old_only_list:
        # print(song)

    return old_to_new_mapping


# used once to fill in "Cover Artist" field added to database
def get_cover_artist(file: Path) -> str:
    if file.is_relative_to(UNOFFICIALV3_DIR):
        trackInfo = tinytag.TinyTag.get(file)
        trackJSon = json.loads(trackInfo.other['comment'][0])
        return trackJSon['CoverArtist']
    elif file.is_relative_to(DRIVE_DIR):
        if "/Duet" in str(file) or "/Anniversary" in str(file):
            return "Neuro & Evil"
        elif "/Evil" in str(file):
            return "Evil"
        elif "/v2 voice" in str(file):
            return "Neuro [v2]"
        elif "/v1 voice" in str(file):
            return "Neuro [v1]"
        else:
            return "Neuro"
    elif file.is_relative_to(CUSTOM_DIR):
        if "Study-sama" in str(file):
            return "Study-sama"
        else:
            return None
    elif file.is_relative_to(OFFICIAL_RELEASE_DIR):
        return None
    else:
        return None
    # These last few return None because the bulk of songs are covered by the other cases and there will be few enough songs left to manually update in a reasonable time


def do_song_titles_match(existing_song_title: str, new_song_title: str) -> bool:
    # print("do_song_titles_match:existing: " + existing_song_title)
    # print("do_song_titles_match:new: " + new_song_title)

    if existing_song_title.startswith('Numbers') and new_song_title.startswith('Numbers'):
        if existing_song_title == 'Numbers' and new_song_title == 'Numbers':
            return True
        elif existing_song_title == 'Numbers II' and new_song_title == 'Numbers II':
            return True
        elif existing_song_title == 'Numbers III' and new_song_title == 'Numbers III':
            return True
        else:
            return False

    songTitleNonAlphaNumStripRegex = r'[^a-z0-9\/]'

    new_title = re.sub(songTitleNonAlphaNumStripRegex, '', str(remove_accents(new_song_title)).lower())
    existing_title = re.sub(songTitleNonAlphaNumStripRegex, '', str(remove_accents(existing_song_title)).lower())

    # print(new_title)
    # print(existing_title)

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

    # print(titles_match)

    return titles_match

def get_song_artists_match_count(existing_song_artists: str, new_song_artists: str) -> int:
    # print("get_song_artists_match_count:new: " + new_song_artists)
    # print("get_song_artists_match_count:existing: " + existing_song_artists)

    artistCharacterStripRegex = r'[\_\-\(\)\[\]\{\}\<\>\.\*\/\'\\]'
    artistStripProducerPRegex = r'p$'
    artistNameSplitRegex = r',|&|\+|( [xX] )'

    # TODO if needed add special case for September - Earth, Wind & Fire

    existing_artists = re.split(artistNameSplitRegex,  str(re.sub(artistStripProducerPRegex, '', re.sub(artistCharacterStripRegex, '', str(remove_accents(existing_song_artists))).lower())))
    new_artists = re.split(artistNameSplitRegex,  str(re.sub(artistStripProducerPRegex, '', re.sub(artistCharacterStripRegex, '', str(remove_accents(new_song_artists))).lower())))

    # print(new_artists)
    # print(existing_artists)

    artists_match_count = 0

    for existing_artist in existing_artists:
        for new_artist in new_artists:
            if re.sub(' ', '', str(new_artist)) in re.sub(' ', '', str(existing_artist)):
                artists_match_count += 1

    # print(artists_match_count)

    return artists_match_count

def remove_accents(s):
   return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

english_title_translation_regex = r'\(.*?\)'
# TODO load from file
title_ascii_special_negative_cases = [
    'short',
    'da ba dee',
    'jp ver.',
    'gotta catch em all',
    'nightcore',
    'chipmunk ver.',
    'me',
    'you',
    'ski-ba-bop-ba-dop-bop',
    'neuro ver.',
    'evil ver.',
    '2023', '2024', '2025',
    'birthday ver.',
    'bread',
    'karaoke ver.',
    'sad cat ver.',
    'what about us',
    'lets lament',
    'i believe in you',
    '500 miles',
    'o',
    'acoustic',
    'number one victory royal',
    'ive had',
    'dont fear',
    'out your eyes then drown you to death',
    'christmas version',
]

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
    # TODO why doesn't this work
    # return s.translate(ascii_character_replacement_mapping)

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
    # print()
    # print('do_songs_match')
    # print()
    # print(s1)
    # print(s2)
    # print()
    
    artists_match = get_song_artists_match_count(s1['Artist'], s2['Artist']) > 0 or get_song_artists_match_count(s2['Artist'], s1['Artist']) > 0
    titles_match = do_song_titles_match(s1['Song'], s2['Song']) or do_song_titles_match(s2['Song'], s1['Song'])
    dates_match = ('Date' not in s2.keys() or s1['Date'] == s2['Date']) or ignore_date
    cover_artists_match = s1['Cover Artist'] == s2['Cover Artist']
    final_result = artists_match and titles_match and dates_match and cover_artists_match

    # print(f'artists match: {artists_match}')
    # print(f'titles match: {titles_match}')
    # print(f'dates match: {dates_match}')
    # print(f'cover artists match: {cover_artists_match}')
    # print(f'final result: {final_result}')

    return final_result

def does_matching_song_exist_in_list(song: SongEntry, lst: list[SongEntry]) -> int:
    """returns count of matching songs in list"""
    match_count = 0
    for entry in lst:
        # print(song)
        # print(entry)
        # print()
        if do_songs_match(song, entry):
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
