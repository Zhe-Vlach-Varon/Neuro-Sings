"""Utility functions for the whole module"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TextIO

# Single import on purpose (loguru only exposes `logger` at package level): the alias below keeps
# every `logger.xxx` call site, while the module itself is needed for the `loguru.Message` type hint.
import loguru
import xxhash
from mutagen.id3 import ID3, ID3NoHeaderError

from . import get_project
from .artists import Project

logger = loguru.logger

SongEntry = dict[str, str | None]
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
    is_old = datetime.now(tz=UTC).timestamp() - file.stat().st_ctime > 7 * 86400
    # File is >2MiB
    is_big = file.stat().st_size > (2 << 20)  # Multiplies by 1024 instead of 1000
    return is_old or is_big


def format_logger(*, log_file: Path | None = None, verbosity: int = 5) -> None:
    """Formats a loguru logger, can be called from anywhere to set it up.

    Args:
        log_file (Path, optional): File to store the logs. Defaults to "logs/neuro.log".
        verbosity (int, optional): Level of verbosity [0-6], the higher the more verbose, see VERBOSE\
            Variable in this file for more details. Defaults to 5 (DEBUG).

    Raises:
        ValueError: If verbosity isn't in [0,6].
    """
    if log_file is None:
        log_file = Path("logs") / "neuro.log"

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
        err = f"File '{file!s}' not found."
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
    logger.info(f"Calculating hash of {file_path}")
    try:

        try:
            audio_tags = ID3(file_path)
            header_size = audio_tags.size  # Mutagen provides the full tag size including header
        except ID3NoHeaderError:
            header_size = 0

        file_size = file_path.stat().st_size
        if file_size < 3000:
            logger.error(f"{file_path.name} is too small!")
            return None

        with open(file_path, 'rb') as f:
            footer_size = 0
            f.seek(-128, 2) # Seek 128 bytes from the end (2)
            if f.read(3) == b'TAG':
                footer_size = 128
            

            if (file_size - footer_size - 1_000_000) > 987: # check to prevent negative indexes
                end_index = file_size - footer_size - 1_000_000 ### about a Mb offset for the audio

            else:
                end_index = int((file_size - footer_size - header_size) * 3 / 4 + header_size)

            logger.debug(f"End Index: {end_index}")

            start_index = end_index - 987 ### reads a 987 bytes for the hash

            f.seek(start_index)
            raw_audio = f.read(987)

        # 4. Hash the raw audio
        return xxhash.xxh64(raw_audio).hexdigest()

    except (OSError, ValueError) as e:
        logger.error(f"Error processing {file_path}: {e}")
        return None

def get_audio_hash_to_file_mapping(p: Path, *, filetype: str = "mp3", max_workers: int = 1) -> dict[str, Path]:
    """Builds the {audio hash: file path} map for every file under p.

    Args:
        p (Path): Directory to scan recursively.
        filetype (str, optional): Extension to consider. Defaults to "mp3".
        max_workers (int, optional): Concurrent hashing threads. Keep 1 on fast local storage —
            profiled here on 2026-09-04: serial won (~0.7s for 1580 files, more workers slower).
            Raise to 4-8 when the files live on slow/networked storage (rclone mounts), where
            hashing is I/O-bound and threads scale near-linearly.

    Returns:
        dict[str, Path]: Audio hash → file path (files that can't be hashed are skipped with a warning).
    """
    files = list(p.glob(f"**/*.{filetype}"))

    if max_workers > 1 and len(files) > 1:
        # Hashing is pure I/O (open/seek/read of a small window), so it's thread-safe as written.
        # map() preserves the input order, keeping the mapping (and its log output) deterministic.
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hash") as executor:
            hashes = list(executor.map(get_audio_hash, files))
    else:
        hashes = [get_audio_hash(file) for file in files]

    file_mapping: dict[str, Path] = {}
    for file, file_hash in zip(files, hashes):
        if file_hash is None:
            # Never insert a None key: it would collapse all failed files into one bucket,
            # and a song with NULL Hash_IN could then match an arbitrary file.
            logger.warning(f"Skipping {file}: audio hash could not be computed")
            continue
        file_mapping[file_hash] = Path(file)

    return file_mapping

# Compiled once at module level instead of on every call.
TITLE_STRIP_RE = re.compile(r'[^a-z0-9\/&]')  # keeps only a-z, 0-9, / and & (titles are lowercased before use)
NIGHTCORE_RE = re.compile(r'((nightcore|chipmunk)(ver(sion)?)?)')

def do_song_titles_match(existing_song_title: str, new_song_title: str) -> bool:
    """Checks whether two titles refer to the same song (case/accent/punctuation-insensitive).

    Args:
        existing_song_title (str): Title already in a list/database.
        new_song_title (str): New title to compare against it.

    Returns:
        bool: True if the titles are considered matching.
    """
    if existing_song_title is None or new_song_title is None:
        return False

    # The "Numbers" series has several near-identical entries ("Numbers", "Numbers II", ...), so it
    # must match exactly instead of falling through to the substring check below.
    if existing_song_title.startswith('Numbers') and new_song_title.startswith('Numbers'):
        return existing_song_title == new_song_title

    new_title = TITLE_STRIP_RE.sub('', str(remove_accents(new_song_title)).lower())
    existing_title = TITLE_STRIP_RE.sub('', str(remove_accents(existing_song_title)).lower())

    # A nightcore/chipmunk version only matches if BOTH titles are (or aren't) one.
    new_is_nightcore = bool(NIGHTCORE_RE.search(new_title))
    if new_is_nightcore:
        new_title = NIGHTCORE_RE.sub('', new_title)

    existing_is_nightcore = bool(NIGHTCORE_RE.search(existing_title))
    if existing_is_nightcore:
        existing_title = NIGHTCORE_RE.sub('', existing_title)

    # Both titles are already lowercased above, so no str.lower() is needed for the comparison.
    return (new_title in existing_title) and (new_is_nightcore == existing_is_nightcore)

# Compiled once at module level instead of on every call.
ARTIST_CHAR_STRIP_RE = re.compile(r"[\_\-\(\)\[\]\{\}\<\>\.\*\/\'\\]")
ARTIST_PRODUCER_P_RE = re.compile(r'p$')  # strips a trailing "p" (producer suffix)
ARTIST_SPLIT_RE = re.compile(r',|&|\+|( [xX] )')

def _split_artist_names(artists: str) -> list[str]:
    """Normalizes an artist string and splits it into individual names.

    Args:
        artists (str): Raw artist field (e.g. "Neuro & Evil, Vedal").

    Returns:
        list[str]: Individual artist names, lowercased and stripped of punctuation.
    """
    cleaned = ARTIST_CHAR_STRIP_RE.sub('', str(remove_accents(artists)).lower())
    parts = ARTIST_SPLIT_RE.split(ARTIST_PRODUCER_P_RE.sub('', cleaned))
    # re.split inserts None where the capturing group didn't participate (e.g. a "," separator); drop those.
    return [part for part in parts if part is not None]


def get_song_artists_match_count(existing_song_artists: str, new_song_artists: str) -> int:
    """Counts how many artist names of `new_song_artists` appear in `existing_song_artists`.

    Args:
        existing_song_artists (str): Artist field of an already known song.
        new_song_artists (str): Artist field to compare against it.

    Returns:
        int: Number of matching artist names (0 = no match).
    """
    artists_match_count = 0
    for existing_artist in _split_artist_names(existing_song_artists):
        for new_artist in _split_artist_names(new_song_artists):
            if new_artist.replace(' ', '') in existing_artist.replace(' ', ''):
                artists_match_count += 1

    return artists_match_count

def remove_accents(s):
   return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

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

ascii_character_replacement_mapping = {
    '’': '\'',
    '＊': '*',
    '★': ' ',
    '  ': ' ',
    ';': '',
}

non_ascii_char_regex = re.compile(r'[^a-zA-Z0-9\-\,\. ]')  # compiled once at module level

def replace_non_ascii_chars(s: str) -> str:
    for key, replacement in ascii_character_replacement_mapping.items():
        s = s.replace(key, replacement)
    return non_ascii_char_regex.sub('', s)

def do_songs_match(s1: SongEntry, s2: SongEntry, ignore_date: bool = False) -> bool:
    
    artists_match = get_song_artists_match_count(s1['Artist'], s2['Artist']) > 0 or get_song_artists_match_count(s2['Artist'], s1['Artist']) > 0
    titles_match = do_song_titles_match(s1['Title'], s2['Title']) or do_song_titles_match(s2['Title'], s1['Title'])
    identifys_match = do_song_titles_match(s1['Identify'], s2['Identify']) or do_song_titles_match(s2['Identify'], s1['Identify'])
    dates_match = ('Date' not in s2 or s1['Date'] == s2['Date']) or ignore_date
    cover_artists_match = s1['Cover Artist'] == s2['Cover Artist']
    final_result = artists_match and titles_match and dates_match and cover_artists_match and identifys_match


    return final_result

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
        setlists_dir = get_project().setlists_dir
        setlists = list(setlists_dir.glob("**/*"))
        for setlist in setlists:
            if setlist.name == 'Setlists.md' or setlist.is_dir():
                continue
            if setlist.is_relative_to(setlists_dir / 'v3 voice' / 'non-karaoke'):
                non_karaoke_albums.append(setlist.stem)
    return non_karaoke_albums


# Replacements for characters that are forbidden/awkward in filenames (module-level so it's built once).
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

MULTI_SPACE_RE = re.compile(r" {2,}")  # runs of spaces left by the replacements above


def sanitize_filename(filename: str) -> str:
    for char, replacement in FORBIDDEN_CHARS.items():
        filename = filename.replace(char, replacement)

    # Collapse the double (or more) spaces created by the replacements above, e.g. " backslash ".
    filename = MULTI_SPACE_RE.sub(' ', filename)

    ## some kanji were getting divided into two symbols: ヴ -> ウ  ゙
    filename = unicodedata.normalize('NFC', filename)

    return filename

_copyright_entries = []

def _load_copyright_entries() -> list:
    """Load and cache copyright_issues.csv entries (loaded once per process)."""
    if not _copyright_entries:
        copyright_file = get_project().data_dir / "copyright_issues.csv"
        if copyright_file.exists():
            with open(copyright_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='|')
                for row in reader:
                    _copyright_entries.append({
                        'title': row.get('title', '').strip(),
                        'artist': row.get('artist', '').strip(),
                    })
    return _copyright_entries

def is_copyright_issue(title: str | None, artist: str | None) -> bool:
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

def get_flags(song: SongEntry, project: Project | None = None) -> str:

    """ Singing voice version: 'v1', 'v2', 'v3', ''
        Lead singer: singer flag from project (e.g. 'neuro', 'evil')
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

    if project is None:
        project = get_project()

    flags: str = ""

    cover_artist = song['Cover Artist']
    lead_singer = song['Lead Singer']

    if lead_singer in project.arg_singers:
        return 'arg;'

    first_artist_flag = project.artists[0].flag
    if '[v1]' in cover_artist:
        flags = f'v1;{first_artist_flag};'
    elif '[v2]' in cover_artist:
        flags = f'v2;{first_artist_flag};'
    else:
        flags = 'v3;'
        if lead_singer in project.singer_names():
            flags += project.flag_for(lead_singer) + ';'
    if cover_artist == project.duet_cover_artist():
        flags += 'duet;'
    elif any(s in cover_artist for s in project.singer_names()) and (
        (' & ' in cover_artist or ', ' in cover_artist) and cover_artist != project.duet_cover_artist()
    ):
        flags += 'collab;'

    return post_process_flags(flags, song['Cover Artist'], project=project)


def post_process_flags(flags: str, cover_artist: str, *, project: Project | None = None, is_twin_duet: bool = False) -> str:
    """Apply post-processing transformations to a flags string.

    1. If is_twin_duet: remove all singer flags (twin-duet streams don't get per-voice flags).
    2. If cover_artist is the project duet name and 'original' is in flags: remove singer flags, ensure 'duet;' is present.
    """
    if project is None:
        project = get_project()

    singer_flags = project.all_singer_flags()  # e.g. ('neuro;', 'evil;')
    if is_twin_duet:
        for sf in singer_flags:
            flags = flags.replace(sf, '')

    if cover_artist == project.duet_cover_artist() and 'original' in flags:
        for sf in singer_flags:
            flags = flags.replace(sf, '')
        if 'duet;' not in flags:
            flags += 'duet;'

    return flags
