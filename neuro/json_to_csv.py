import json
import re
from pathlib import Path
from typing import Literal, Optional

import polars as pl
from loguru import logger

from neuro import ROOT_DIR, DATES_CSV, LOG_DIR, SETLISTS_DIR, SONGS_CSV, SONGS_DB, SONGS_JSON
from neuro.polars_utils import load_dates, load_db, songs_schema, dates_schema
import neuro.utils as neutils

from tqdm import tqdm


def is_eliv(s: neutils.SongEntry) -> bool:
    """Checks if the file from an Entry is sung by Evil.

    Args:
        s (SongEntry): Song Entry.

    Returns:
        bool: True if it's sung by Evil.
    """
    if s["File_IN"] is not None:
        return "Evil.v" in s["File_IN"]
    else:
        return False

def is_duet(s: neutils.SongEntry) -> bool:
    """Checks if the file from an Entry is a duet.

    Args:
        s (SongEntry): Song Entry.

    Returns:
        bool: True if it's in the subfolder.
    """
    assert s["File_IN"] is not None
    return "(Duet.v" in s["File_IN"] and "Neuro & Evil)" in s["File_IN"]


def is_eliv_old(s: neutils.SongEntry) -> bool:
    """Checks if the file from an Entry is in the Evil subdirectory.

    Args:
        s (SongEntry): Song Entry.

    Returns:
        bool: True if it's in the subfolder.
    """
    assert s["File_IN"] is not None
    return "/Evil" in s["File_IN"]


def field_ascii(song: neutils.SongEntry, field: Literal["Song", "Artist"]) -> tuple[str, str]:
    """Gets the "normal" and "ASCII" versions of the 2 fields that have these variants.

    Args:
        song (SongEntry): A song Entry (dict from JSON file).
        field (Literal["Song", "Artist"]): The field.

    Returns:
        tuple[str, str]: A tuple with (normal, ascci).
    """
    normal = song[f"{field}"]
    assert normal is not None

    ascii = song.get(f"{field}_ASCII", normal)
    assert ascii is not None

    return normal, ascii


def get_flags_old(file: Path, eliv: Optional[bool] = None) -> Optional[str]:
    """Gets the common evil/duet flag given a file. Evil flag can be set from \
        another boolean.

    Args:
        file (Path): File to check
        eliv (Optional[bool], optional): Can be ignored, but in case of an evil \
            stream, the duets will be in `/Duets` and not `/Evil`, so a global flag\
            for the stream can be given. Defaults to None.

    Returns:
        Optional[str]: String with flags if any, None otherwise.
    """
    flags = ""

    # get Neuro version
    if ".v1" in str(file) and "Evil" not in str(file) and "Duet" not in str(file):
        flags = "v1;"
    elif ".v2" in str(file) and "Evil" not in str(file) and "Duet" not in str(file):
        flags = "v2;"
    elif "Neuro.v3" in str(file) or "Evil.v" in str(file) or "Duet.v" in str(file):
        flags = "v3;"

    # get lead singer
    if eliv is None:
        if "Evil.v" in str(file) :
            flags += "evil;"
    elif eliv:  # eliv is not None, then it's a bool, and here the bool is True
        flags += "evil;"
    else:
        flags += "neuro;"
        
    # get duet
    if "Duet.v" in str(file) and "(Neuro & Evil)" in str(file):
        flags += "duet;"
    elif "Duet.v" in str(file) and "(Neuro & Evil)" not in str(file):
        flags += "collab;"

    # additional tags
    if "officially released songs" in str(file):
        flags += "official;"
        
    # Null out flags if empty
    # should never be empty, should always have at least version and lead singer
    if flags == "":
        flags = None

    return flags

def get_flags(song: neutils.SongEntry) -> str:

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
    
    return flags


def update_db() -> None:
    """Updates the song database, adding songs from the JSON file that aren't yet in it
    The Date CSV/Table is also updated for each new stream"""
    neutils.format_logger(log_file=LOG_DIR / "json.log")
    with open(SONGS_JSON, "r") as f:
        json_data: neutils.SongJSON = json.load(f)

    # Absolutely doesn't work if the CSV is empty
    songs_df = load_db()
    dates_df = load_dates()

    non_karaoke_albums = neutils.get_non_karaoke_album_names()

    if songs_df.height == 0:
        songs_df = pl.DataFrame({}, schema=songs_schema)
    
    if dates_df.height == 0:
        dates_df = pl.DataFrame({}, schema=dates_schema)

    # [-1] Makes sure id=0 if the column is empty
    id = max(songs_df.get_column("id").to_list() + [-1]) + 1

    streams_done: list[str] = []

    album_names: list[str] = []

    # date is like 2025-04-02
    # songs is a list of dict with song infos
    for album, songs in json_data.items():
        # eliv = sum(map(is_eliv, songs)) > 0 # this assumed that only one twin would main in a karaoke stream, which is now false, as of 2025-12-25 Christmas Karaoke, where Neuro started the set, then swapped to Evil for second half
        # singer = "Evil" if eliv else "Neuro"

        if album not in non_karaoke_albums:
            twin_duet_stream = True
        else:
            twin_duet_stream = False
        
        if twin_duet_stream:
            for song in songs:
                twin_duet_stream = twin_duet_stream and song['Cover Artist'] == 'Neuro & Evil'
                if not twin_duet_stream:
                    break

        # get date from song JSON object
        for song in songs:
            # print(song)
            if 'Date' in song.keys():
                date = song["Date"]
                named_album = True
            else:
                date = album
                named_album = False
            singer = song['Cover Artist']
            if singer == 'Neuro & Evil':
                singer = "Twins"
            eliv = song['Lead Singer'] == "Evil"
            # print("adding dates to database")
            # print(date)
            if date[0] == "2" and date not in dates_df.get_column("Date") and date > "2023-06-08" and song['Cover Artist'] in ['Neuro', 'Evil', 'Neuro & Evil']:
                duet_format: str
                if date >= '2025-03-25':
                    duet_format = 'v2'
                elif date >= '2024-12-19':
                    duet_format = 'v2v1'
                else:
                    duet_format = 'v1'
                df = pl.DataFrame(
                    {
                        "Date": date,
                        "Singer": singer,
                        "Duet Format": duet_format,
                    }
                )
                # Adds a row for a new stream in the dates CSV
                dates_df.extend(df)
                logger.info(f"[Karaoke][+] {date} with {singer} singing")
        
        remove = 0
        # Just ensures that when sorting by id, the songs from a same album will also be sorted
        for song in sorted(songs, key=lambda x: x["id"] if x["id"] is not None else 5000):
            if song["id"] is None:
                continue

            date = song["Date"]

            # print(f"{song["Song"]} - {song["Artist"]} - {song["Cover Artist"]} - {song['Date']}")

            if "duplicate" not in song.keys():
                song["duplicate"] = False

            if not song["duplicate"] and "File_IN" not in song.keys():
                print("How did we get here ?!")
                print("Song is not duplicate but has no File_IN")
                print("")
                print(song)
                exit(1)

            if not song["duplicate"]:
                # print(song)
                file = Path(song["File_IN"])
                neutils.file_check(file)  # Checks if file exists on disk
            else:
                file = None

            # TODO check if duplicate
            # TODO sort list of songs by date so that duplicates don't get added before first instance
            if file is not None and str(file) in songs_df.get_column("File_IN") and not song["duplicate"]:
                remove += 1
                logger.debug(f"File {str(file)} was already in database")
                continue

            # Using helper function to avoid code duplication
            # print(song)
            name, name_ascii = field_ascii(song, "Song")
            artist, artist_ascii = field_ascii(song, "Artist")

            # date is assumed to be a date used to form the album title, and if not a date is used as the album title
            # if str(date).startswith("20"):
                # album = f"{singer} {date} Karaoke" # move this to detection, and replace date with album here
            # else:
                # album = date


            if 'Image' in song.keys() and not song['Image'] == "":
                cover_image = song["Image"]
                # if not cover_image is None:
                    # print("cover image: " + cover_image)
                # else:
                    # print("using default cover image system")
            else:
                cover_image = None
                # print("cover image: None")

            in_hash = None

            if not song['duplicate']:
                in_hash = neutils.get_audio_hash(file)

            # flags = get_flags(file, eliv)
            flags = get_flags(song)
            assert flags is not None
            flags += song['additional flags']

            if twin_duet_stream:
                pre_replace_flags = flags
                # print(f'twin stream: yes: pre-replace: {flags}')
                flags = flags.replace('evil;', '').replace('neuro;', '')
                # print(f'twin stream: yes: post-replace: {flags}')
                assert pre_replace_flags != flags

            if song['Cover Artist'] == 'Neuro & Evil' and 'original' in flags:
                flags = flags.replace('neuro;', '').replace('evil;', '')
                if 'duet;' not in flags:
                    flags += 'duet;'


            if song['encore']:
                name += ' - Encore'
                name_ascii += ' - Encore'

            df = pl.DataFrame(
                {
                    "id": id,
                    "Song": name,
                    "Artist": artist,
                    "Song_ASCII": name_ascii,
                    "Artist_ASCII": artist_ascii,
                    "Cover Artist": song["Cover Artist"],
                    "Date": date,
                    "Album": album,
                    "Album_ID": song["id"],
                    "Image": cover_image,
                    "File_IN": str(file),
                    "Hash_IN": in_hash,
                    "Flags": flags,
                    "Key": None,
                    "Tempo (1/4 beat)": None,
                    'Version': song['Version'],
                }
            )
            # with pl.Config(tbl_cols=-1):
                # print(df)
            if song["duplicate"]:
                # print(song)
                # print(song['duplicate'])
                # print(song['encore'])
                df = get_most_recent_version(df.to_dicts()[0], json_data, song['encore'], song['Lead Singer'])

            id += 1
            remove += 1
            # with pl.Config(tbl_cols=-1):
                # print(songs_df.tail(5))
                # print(df)
            songs_df.extend(df)
            logger.info(f"[Song][+] {artist} - {name}")

        if remove == len(songs):
            if named_album:
                album_names.append(album)
            else:
                streams_done += [date]

    for date in streams_done:
        json_data.pop(album)
        logger.info(f"All songs from {date} treated, removed stream")
    for album in album_names:
        json_data.pop(album)
        logger.info(f"All songs from {album} treated, removed stream")


    # Updates JSON file with treated songs removed
    with open(SONGS_JSON, "w") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    sorted_songs_df = songs_df.sort(['Date', 'Album', 'Album_ID'])
    sorted_dates_df = dates_df.sort('Date')

    sorted_songs_df = sorted_songs_df.with_columns(pl.int_range(0, pl.len(), dtype = pl.Int64).alias('id'))
    
    # Write modifications if both CSVs
    sorted_songs_df.write_csv(SONGS_CSV)
    sorted_dates_df.write_csv(DATES_CSV)
    # Write modifications if DBs
    sorted_songs_df.write_database("Songs", f"sqlite:///{SONGS_DB}", if_table_exists="replace")
    sorted_dates_df.write_database("Dates", f"sqlite:///{SONGS_DB}", if_table_exists="replace")


# Shouldn't ever need to use this again, was used to update database after switching from using file hashes to using hashes of the audio data
def update_db_hashes() -> None:
    songs = load_db()
    schema = songs.schema

    new_songs_df = pl.DataFrame(schema=schema)

    for song in tqdm(songs.iter_rows(named=True), total=len(songs)):
        file = ROOT_DIR / Path(song["File_IN"])
        # print(file)
        assert file.exists()
        hash = song["Hash_IN"]
        # print(get_audio_hash(file))
        if neutils.get_audio_hash(file) != hash:
            song["Hash_IN"] = neutils.get_audio_hash(file)
        new_songs_df.extend(pl.DataFrame(song))
            
    new_songs_df.write_csv(SONGS_CSV)
    new_songs_df.write_database("Songs", f"sqlite:///{SONGS_DB}", if_table_exists="replace")

# def update_database_file_in_fields() -> None:
#     # TODO

def add_cover_artist() -> None:
    songs = load_db()
    schema = songs.schema
    # print(schema)

    new_songs_df = pl.DataFrame(schema=schema)

    for song in tqdm(songs.iter_rows(named=True), total=len(songs)):
        file = ROOT_DIR / Path(song["File_IN"])
        # print(file)
        assert file.exists()
        singer = neutils.get_cover_artist(file)
        song["Cover Artist"] = singer
        new_songs_df.extend(pl.DataFrame(song))
            
    new_songs_df.write_csv(SONGS_CSV)
    new_songs_df.write_database("Songs", f"sqlite:///{SONGS_DB}", if_table_exists="replace")


def get_most_recent_version(song: dict, json_data: neutils.SongJSON, encore: bool, lead_singer: str) -> pl.DataFrame:
    # if json for song has duplicate true, search database for most recent version of song with same singer
    # either detect singer from existing data, or add cover_artist field to database
    songDB = load_db()

    # print(song['Album'][0])

    latest_version = None

    filtered_songs = songDB.filter(
        (pl.col("Artist").map_elements(lambda x: neutils.get_song_artists_match_count(x, song['Artist'][0]) > 0, return_dtype=pl.Boolean)) &
        (pl.col("Song").map_elements(lambda x: neutils.do_song_titles_match(x, song['Song'][0]), return_dtype=pl.Boolean)) &
        (pl.col("Cover Artist") == song["Cover Artist"][0]) &
        (pl.col("Date") <= song["Date"][0]) &
        (~pl.col("Flags").str.contains("duplicate"))
    ).sort(pl.col("Date"), descending=True)

    # print("filtered_songs")
    # print(filtered_songs)
    # print("get_most_recent_version:song")
    # print(song)
    # TODO if filtered_songs.height is 0, check the the new_songs JSONObject and find the most recent version that is not the current song
    #          will need this for karaoke setlists that have an encore
    # TODO make sure that when searching for previous versions, to not consider songs with a later date, and also not songs with a later track number

    filtered_json_songs = []

    # print(song)
    # TODO filter json data
    for album, json_songs in json_data.items():
        # print(album)
        for json_song in json_songs:
            # print(json.dumps(json_song))
            # print(song)
            # print(json_song)
            # print('new: ' + song['Song'][0] + " - " + song['Artist'][0] + " - " + song['Cover Artist'][0] + " - " + song['Date'][0] + " - " + str(song['Album_ID'][0]))
            # print('old: ' + json_song['Song'] + " - " + json_song['Artist'] + " - " + json_song['Cover Artist'] + " - " + json_song['Date'] + " - " + str(json_song['id']))
            # print((get_song_artists_match_count(json_song['Artist'], song['Artist'][0]) or get_song_artists_match_count(song['Artist'][0], json_song['Artist'])) and do_song_titles_match(json_song["Song"], song["Song"][0]) and (json_song["Cover Artist"] == song["Cover Artist"][0]) and ((song["Date"][0] >= json_song["Date"]) or (not json_song["id"] == song['Album_ID'][0])) and "File_IN" in json_song.keys())
            # print((get_song_artists_match_count(json_song['Artist'], song['Artist'][0]) or get_song_artists_match_count(song['Artist'][0], json_song['Artist'])))
            # print(do_song_titles_match(json_song["Song"], song["Song"][0]))
            # print((json_song["Cover Artist"] == song["Cover Artist"][0]))
            # print(((song["Date"][0] >= json_song["Date"]) or (not json_song["id"] == song['Album_ID'][0])) and "File_IN" in json_song.keys())
            # print()
            if (neutils.do_songs_match(song, json_song, ignore_date=True)) and ((song["Date"] >= json_song["Date"]) or (not json_song["id"] == song['Album_ID'])) and "File_IN" in json_song.keys():
                # print("adding song to filtered songs")
                filtered_json_songs.append(json_song)
            # print()

    # TODO sort filtered json data
    sorted_filtered_json_songs = sorted(filtered_json_songs, key=lambda d:  d['Date'])                              
    # print(sorted_filtered_json_songs)

    # print(sorted_filtered_json_songs)

    # print("songs filtered")
    # print(filtered_songs.height)
    # print(len(filtered_json_songs))

    latest_db_version = None
    latest_json_version = None

    if filtered_songs.height > 0:
        latest_db_version = filtered_songs.row(0, named=True)
        db_flags = latest_db_version["Flags"]
    if len(filtered_json_songs) > 0:
        latest_json_version = sorted_filtered_json_songs[0]
        # add way to specify flags in setlist files
        # json_flags = get_flags(latest_json_version['File_IN'])
        json_flags = get_flags(latest_json_version)

    if not latest_db_version is None:
        if not latest_json_version is None:
            if latest_json_version['Date'] >= latest_db_version['Date']:
                latest_version = latest_json_version
                flags = json_flags
            else:
                latest_version = latest_db_version
                flags = db_flags
        else:
            latest_version = latest_db_version
            flags = db_flags
    elif not latest_json_version is None:
        latest_version = latest_json_version
        flags = json_flags
    else:
        print("How did we get here?!")
        print("check for typos in setlists")
        print(song['Album'])
        for key in song.keys():
            print(f'{key}: {song[key]}')
        # with open("get_most_recent_version_json_data.txt", "w") as f:
        #     json.dump(json_data, f, indent=4)
        exit(1)


    # print("latest_version")
    # print(latest_version)

    # TODO get latest version of the two from json and db

    # already checked that flags does not contain duplicate when filtering
    flags += "duplicate;"
    
    if encore:
        flags += 'encore;'

    if lead_singer == 'Neuro':
        flags = flags.replace('evil', 'neuro')
    if lead_singer == 'Evil':
        flags = flags.replace('neuro', 'evil')

    # print(song)
    entry_flags = song['Flags'].split(';')
    for fl in entry_flags:
        if fl not in flags:
            flags += f'{fl};'

    if filtered_songs.height > 0 and latest_version == latest_db_version:
        new_duplicate_song = pl.DataFrame(
        {
               "id": song["id"],
               "Song": latest_version["Song"] if not encore else latest_version["Song"] + ' - Encore',
               "Artist": latest_version["Artist"],
               "Song_ASCII": latest_version["Song_ASCII"] if not encore else latest_version["Song_ASCII"] + ' - Encore',
               "Artist_ASCII": neutils.replace_non_ascii_chars(song["Artist_ASCII"]),
               "Cover Artist": latest_version["Cover Artist"],
               "Date": song["Date"],
               "Album": song["Album"],
               "Album_ID": song["Album_ID"],
               "Image": song["Image"],
               "File_IN": latest_version["File_IN"],
               "Hash_IN": latest_version["Hash_IN"],
               "Flags": flags,
               "Key": latest_version["Key"],
               "Tempo (1/4 beat)": latest_version["Tempo (1/4 beat)"],
               "Version": latest_version["Version"],
            }
        )
    elif len(filtered_json_songs) > 0 and latest_version == latest_json_version:
        # print(song)
        # print(latest_version)
        new_duplicate_song = pl.DataFrame(
        {
               "id": song["id"],
               "Song": latest_version["Song"] if not encore else latest_version["Song"] + ' - Encore',
               "Artist": latest_version["Artist"],
               "Song_ASCII": latest_version["Song_ASCII"] if not encore else latest_version["Song_ASCII"] + ' - Encore',
               "Artist_ASCII": neutils.replace_non_ascii_chars(song["Artist_ASCII"]),
               "Cover Artist": latest_version["Cover Artist"],
               "Date": song["Date"],
               "Album": song["Album"],
               "Album_ID": song["Album_ID"],
               "Image": song["Image"],
               "File_IN": latest_version["File_IN"],
               "Hash_IN": neutils.get_audio_hash(Path(latest_version["File_IN"])),
               "Flags": flags,
               "Key": song["Key"],
               "Tempo (1/4 beat)": song["Tempo (1/4 beat)"],
               "Version": song["Version"],
            }
        )
    else:
        print("How did we get here?!")
        print("unable to get latest version")
        exit(1)
    # print(song["Image"])

    return new_duplicate_song

if __name__ == "__main__":
    update_db()
