"""Some checks to run on files"""

import os
import tomllib as toml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from neuro import LOG_DIR, ROOT_DIR
from neuro.polars_utils import load_db
from neuro.utils import format_logger, get_audio_hash
from neuro.detection import check_missing_setlist_entries


def check_hash(*, max_workers: int = 1) -> None:
    """Checks if the hash from files match the hash in the database (long).

    All failures are collected and reported at once instead of stopping at the first one.

    Args:
        max_workers (int, optional): Number of concurrent hashing threads. Keep 1 on fast local\
            storage (profiled 2026-09-04: serial won); raise to 4-8 when files live on\
            slow/networked storage (rclone mounts), where hashing is I/O-bound. Defaults to 1.

    Raises:
        AssertionError: If any file is missing or its hash differs from the database.
    """
    songs = load_db()
    rows = list(songs.iter_rows(named=True))

    def _check(song: dict) -> str | None:
        file = ROOT_DIR / Path(song["File_IN"])
        if not file.exists():
            return f"{file}: does not exist"
        if get_audio_hash(file) != song["Hash_IN"]:
            return f"{file}"
        return None

    failures: list[str] = []
    if max_workers > 1 and len(rows) > 1:
        # Hashing is pure I/O and independent per song → safe to run through a thread pool.
        logger.debug(f"Checking {len(rows)} files' hashes ({max_workers} workers)")
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hash-check") as executor, \
             tqdm(total=len(rows), desc="hash check") as pbar:
            futures = [executor.submit(_check, song) for song in rows]
            for future in as_completed(futures):
                failure = future.result()  # re-raises unexpected errors from a worker
                if failure is not None:
                    failures.append(failure)
                pbar.update(1)
    else:
        logger.debug(f"Checking {len(rows)} files' hashes (serial)")
        for song in tqdm(rows, desc="hash check"):
            failure = _check(song)
            if failure is not None:
                failures.append(failure)

    if failures:
        raise AssertionError("hash check failed:\n  " + "\n  ".join(sorted(set(failures))))


# Test if there are case inconsitancies at all
def check_case(field: str) -> None:
    """Checks for any inconsistency in the database regarding casing and logs any found.

    Args:
        field (str): The field to check, usually Title or Artist.
    """
    songs = load_db()
    cased = set()
    uncased = set()
    for song in songs.rows(named=True):
        cased |= {song[field]}
        uncased |= {song[field].lower()}

    if len(cased) != len(uncased):
        logger.warning("Wrong casing detected")

        # Locates errors. A dict maps each lowercased value to the first cased value seen with it,
        # which is an O(1) lookup (a list + .index() inside this loop was O(n²)).
        first_seen: dict[str, str] = {}
        for song in songs.iter_rows(named=True):
            thing = song[field]
            thing_l = thing.lower()
            if thing_l not in first_seen:
                first_seen[thing_l] = thing
            elif first_seen[thing_l] != thing:
                logger.warning(f"{first_seen[thing_l]} != {thing}")
    else:
        logger.success(f"No casing inconsistency found in field '{field}'")


def check_mp3gain() -> None:
    """Checks for the mp3gain executable on the path"""
    with open("config.toml", "rb") as file:
        config = toml.load(file)
    if "mp3gain" in config["features"]["activated"]:
        if os.system("mp3gain -q") != 0:
            logger.error("mp3gain activated, but executable not found")
        else:
            logger.success("mp3gain executable found")
    else:
        logger.info("Not checking for mp3gain as option isn't activated")


def check_are_dbs_identical():
    """Checks that both databases (SQLite and CSV) are identical.

    Raises:
        ValueError: If there are inconsistencies between databses.
    """
    sqlite = load_db(as_db=True)
    csv = load_db(as_db=False)
    if len(sqlite) != len(csv):
        logger.error("Databases have different number of entries")
        raise ValueError("Databases have different number of entries")

    if sqlite.columns != csv.columns:
        logger.error("Databases have different columns")
        raise ValueError("Databases have different columns")

    # Fast column-wise comparison in C; only fall back to the row-by-row Python loop (below) when
    # something actually differs, so the success path never iterates over every cell.
    if sqlite.equals(csv):
        logger.success("Both databases are identical")
        return

    have_differences = False
    for i, (row_sq, row_csv) in enumerate(zip(sqlite.rows(named=True), csv.rows(named=True))):
        # row is a dictionary with the column names as keys
        for key in row_sq.keys():
            message = f"Row {i} differs between databases in column {key}: {row_sq[key]} != {row_csv[key]}"
            if row_sq[key] != row_csv[key]:
                logger.error(message)
                # Allows multiple errors to be reported at once
                have_differences = True
    if have_differences:
        raise ValueError("Databases have different values")
    logger.success("Both databases are identical")


def all_tests() -> None:
    """Runs all checks defined in this file"""
    format_logger(log_file=LOG_DIR / "checks.log")
    check_case("Artist")
    check_case("Title")
    check_hash()
    check_mp3gain()
    check_are_dbs_identical()
    check_missing_setlist_entries()


if __name__ == "__main__":
    all_tests()
