"""Utility functions for the whole module"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TextIO

import hashlib
from mutagen.id3 import ID3, ID3NoHeaderError

import tinytag
import json

import loguru
from loguru import logger

from neuro import LOG_DIR, OFFICIAL_RELEASE_DIR, UNOFFICIALV3_DIR, CUSTOM_DIR, DRIVE_DIR

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


# get_audio_hash function taken from 
# https://github.com/Nyss777/Neuro-Karaoke-Archive-Metadata hash_mutagen.py
# MIT License

# Copyright (c) 2026 Nyss777

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

def get_audio_hash(file_path):
    try:
        try:
            audio_tags = ID3(file_path)
            header_size = audio_tags.size  # Mutagen provides the full tag size including header
        except ID3NoHeaderError:
            header_size = 0

        with open(file_path, 'rb') as f:
            # We read the whole file to handle the footer check
            # For very large files, you can use f.seek() instead of loading everything
            file_data = f.read()

        # 2. Check for ID3v1 footer (always 128 bytes at the end starting with 'TAG')
        # Mutagen doesn't always expose the ID3v1 offset as a single property,
        # so a quick manual check of the last 128 bytes is still standard.
        footer_size = 128 if file_data[-128:].startswith(b'TAG') else 0
        
        # 3. Slice the data to extract only the audio frames
        # If footer_size is 0, file_data[header_size:] takes everything to the end
        end_index = len(file_data) - footer_size
        raw_audio = file_data[header_size:end_index]

        # 4. Hash the raw audio
        return hashlib.md5(raw_audio).hexdigest() # ZVV: using hashlib.md5 instead of xxhash.xxh64 because I cannot get python to recognize it as being installed on my system

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None


def get_audio_hash_to_file_mapping(p: Path, *, filetype: str = "mp3") -> dict:
    print(p)
    files = list(p.glob(f"**/*.{filetype}"))
    file_mapping = {}

    for file in files:
        print(file)
        hash = get_audio_hash(file)
        file_mapping[hash] = Path(file)
    
    return file_mapping

# used once to fill in "Cover Artist" field added to database
def get_cover_artist(file: Path) -> str:
    if file.is_relative_to(UNOFFICIALV3_DIR):
        trackInfo = tinytag.TinyTag.get(file)
        trackJSon = json.loads(trackInfo.other['comment'][0])
        return trackJSon['Cover Artist']
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