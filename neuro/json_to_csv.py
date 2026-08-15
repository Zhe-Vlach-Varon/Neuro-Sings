import json
import re
from pathlib import Path
from typing import Literal, Optional

import polars as pl
from loguru import logger

from neuro import SONG_ROOT_DIR, ROOT_DIR, DATES_CSV, LOG_DIR, SETLISTS_DIR, SONGS_CSV, SONGS_DB, SONGS_JSON, OFFICIAL_RELEASE_DIR
from neuro.polars_utils import load_dates, load_db, songs_schema, dates_schema
import neuro.utils as neutils

from neuro.detection import check_missing_setlist_entries

from tqdm import tqdm


def clear_db() -> None:
    songs_df = pl.DataFrame({}, schema=songs_schema)
    dates_df = pl.DataFrame({}, schema=dates_schema)

    songs_df.write_csv(SONGS_CSV)
    dates_df.write_csv(DATES_CSV)
    
    songs_df.write_database("Songs", f"sqlite:///{SONGS_DB}", if_table_exists="replace")
    dates_df.write_database("Dates", f"sqlite:///{SONGS_DB}", if_table_exists="replace")    


def update_db() -> None:
    """Updates the song database, adding songs from the JSON file that aren't yet in it
    The Date CSV/Table is also updated for each new stream"""
    neutils.format_logger(log_file=LOG_DIR / "json.log")
    with open(SONGS_JSON, "r") as f:
        json_data: neutils.SongJSON = json.load(f)

    songs_df = load_db()
    dates_df = load_dates()

    non_karaoke_albums = neutils.get_non_karaoke_album_names()

    if songs_df.height == 0:
        songs_df = pl.DataFrame({}, schema=songs_schema)
    
    if dates_df.height == 0:
        dates_df = pl.DataFrame({}, schema=dates_schema)

    # [-1] Makes sure id=0 if the column is empty
    id = max(songs_df.get_column("id").to_list() + [-1]) + 1

    album_names: list[str] = []

    dupes_to_process = []

    for album, songs in json_data.items():

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
            if 'Date' in song.keys():
                date = song["Date"]
                named_album = True
            else:
                date = album
                named_album = False
            singer = song['Cover Artist']
            if singer == 'Neuro & Evil':
                singer = "Twins"
            lead_singer = song['Lead Singer']

            if date[0] == "2" and date not in dates_df.get_column("Date") and date > "2023-06-08" and song['Cover Artist'] in ['Neuro', 'Evil', 'Neuro & Evil']:
                if date >= '2025-03-25':
                    duet_format = 'v2'
                elif date >= '2024-12-19':
                    duet_format = 'v2v1'
                else:
                    duet_format = 'v1'
                df = pl.DataFrame(
                    {
                        "Date": date,
                        "Singer": lead_singer if not twin_duet_stream else 'Twins',
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

            if "duplicate" not in song.keys():
                song["duplicate"] = False

            if not song["duplicate"] and "File_IN" not in song.keys():
                logger.error("How did we get here?!")
                logger.error("Song is not duplicate but has no File_IN")
                logger.debug("")
                logger.debug(f"Song: {song}")
                exit(1)

            if not song["duplicate"]:
                file = Path(song["File_IN"])
                neutils.file_check(file)  # Checks if file exists on disk
            else:
                file = None

            if file is not None and str(file) in songs_df.get_column("File_IN") and not song["duplicate"]:
                remove += 1
                logger.debug(f"File {str(file)} was already in database")
                continue

            name = song['Title']
            artist = song['Artist']

            if 'Image' in song.keys() and not song['Image'] == "":
                cover_image = song["Image"]
            else:
                cover_image = None

            in_hash = None

            if not song['duplicate']:
                in_hash = neutils.get_audio_hash(file)

            flags = neutils.get_flags(song)
            assert flags is not None

            if neutils.is_copyright_issue(song['Title'], song['Artist']):
                flags += 'copyright_issues;'

            flags += song['additional flags']

            if twin_duet_stream:
                pre_replace_flags = flags
                flags = flags.replace('evil;', '').replace('neuro;', '')
                if 'evil;' in pre_replace_flags or 'neuro;' in pre_replace_flags:
                    assert pre_replace_flags != flags

            if song['Cover Artist'] == 'Neuro & Evil' and 'original' in flags:
                flags = flags.replace('neuro;', '').replace('evil;', '')
                if 'duet;' not in flags:
                    flags += 'duet;'

            df = pl.DataFrame(
                {
                    "id": id,
                    "Title": song["Title"],
                    "TitleOG": song["TitleOG"],
                    "Identify": song["Identify"],
                    "Artist": song["Artist"],
                    "ArtistOG": song["ArtistOG"],
                    "Cover Artist": song["Cover Artist"],
                    "Lead Singer": song["Lead Singer"],
                    "Date": date,
                    "Album": album,
                    "Album_ID": song["id"],
                    "Image": cover_image,
                    "File_IN": str(file),
                    "Hash_IN": in_hash,
                    "Flags": flags,
                    "Key": None,
                    "Tempo (1/4 beat)": None,
                    "Version": song["Version"],
                    "Special": song["Special"],
                    "Comment": song["Comment"]
                }
            )
            if song["duplicate"]:
                dupes_to_process.append((df, song['encore'], song['Lead Singer']))

            id += 1
            remove += 1
            if not song['duplicate']:
                songs_df.extend(df)
                logger.info(f"[Song][+] {artist} - {name}")

        if remove == len(songs):
            if named_album:
                album_names.append(album)

    for dupe in dupes_to_process:
        songs_df.extend(get_most_recent_version(dupe[0].to_dicts()[0], json_data, dupe[1], dupe[2]))
        logger.info(f"[Song][+] {dupe[0]['Artist'][0]} - {dupe[0]['Title'][0]}")

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

    check_missing_setlist_entries()    

def get_most_recent_version(song: dict, json_data: neutils.SongJSON, encore: bool, lead_singer: str) -> pl.DataFrame:
    # if json for song has duplicate true, search database for most recent version of song with same singer
    # either detect singer from existing data, or add cover_artist field to database
    songDB = load_db()


    latest_version = None

    filtered_songs = songDB.filter(
        (pl.col("Artist").map_elements(lambda x: neutils.get_song_artists_match_count(x, song['Artist']) > 0, return_dtype=pl.Boolean)) &
        (pl.col("Title").map_elements(lambda x: neutils.do_song_titles_match(x, song['Title']), return_dtype=pl.Boolean)) &
        (pl.col("Cover Artist") == song["Cover Artist"]) &
        (pl.col("Date") <= song["Date"]) &
        (~pl.col("Flags").str.contains("duplicate"))
    ).sort(pl.col("Date"), descending=True)

    filtered_json_songs = []

    for album, json_songs in json_data.items():
        for json_song in json_songs:
            if (neutils.do_songs_match(song, json_song, ignore_date=True)) and ((song["Date"] >= json_song["Date"]) or (not json_song["id"] == song['Album_ID'])) and "File_IN" in json_song.keys():
                filtered_json_songs.append(json_song)

    sorted_filtered_json_songs = sorted(filtered_json_songs, key=lambda d:  d['Date'])                              

    latest_db_version = None
    latest_json_version = None

    if filtered_songs.height > 0:
        latest_db_version = filtered_songs.row(0, named=True)
        db_flags = latest_db_version["Flags"]
    if len(filtered_json_songs) > 0:
        latest_json_version = sorted_filtered_json_songs[0]
        json_flags = neutils.get_flags(latest_json_version)

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
        logger.error("How did we get here?!")
        logger.error("check for typos in setlists")
        logger.error(f"Album: {song['Album']}")
        for key in song.keys():
            logger.error(f"{key}: {song[key]}")
        exit(1)

    flags += "duplicate;"
    
    if encore:
        flags += 'encore;'

    if lead_singer == 'Neuro':
        flags = flags.replace('evil', 'neuro')
    if lead_singer == 'Evil':
        flags = flags.replace('neuro', 'evil')

    entry_flags = song['Flags'].split(';')
    for fl in entry_flags:
        if fl not in flags:
            flags += f'{fl};'

    if filtered_songs.height > 0 and latest_version == latest_db_version:
        new_duplicate_song = pl.DataFrame(
        {
               "id": song["id"],
               "Title": latest_version["Title"],
               "TitleOG": latest_version["TitleOG"],
               "Identify": latest_version["Identify"],
               "Artist": latest_version["Artist"],
               "ArtistOG": latest_version["ArtistOG"],
               "Cover Artist": latest_version["Cover Artist"],
               "Lead Singer": latest_version["Lead Singer"],
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
               "Special": latest_version["Special"],
               "Comment": latest_version["Comment"],
            }
        )
    elif len(filtered_json_songs) > 0 and latest_version == latest_json_version:
        new_duplicate_song = pl.DataFrame(
        {
               "id": song["id"],
               "Title": latest_version["Title"],
               "TitleOG": latest_version["TitleOG"],
               "Identify": latest_version["Identify"],
               "Artist": latest_version["Artist"],
               "ArtistOG": latest_version["ArtistOG"],
               "Cover Artist": latest_version["Cover Artist"],
               "Lead Singer": latest_version["Lead Singer"],
               "Date": song["Date"],
               "Album": song["Album"],
               "Album_ID": song["Album_ID"],
               "Image": song["Image"],
               "File_IN": latest_version["File_IN"],
               "Hash_IN": neutils.get_audio_hash(Path(latest_version["File_IN"])),
               "Flags": flags,
               "Key": song["Key"],
               "Tempo (1/4 beat)": song["Tempo (1/4 beat)"],
               "Version": latest_version["Version"],
               "Special": latest_version["Special"],
               "Comment": latest_version["Comment"],
            }
        )
    else:
        logger.error("How did we get here?!")
        logger.error("unable to get latest version")
        exit(1)

    return new_duplicate_song

if __name__ == "__main__":
    update_db()
