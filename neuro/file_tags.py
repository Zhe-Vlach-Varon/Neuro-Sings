"""Applies all metadata tags on music files"""

import os
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from loguru import logger
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3
from mutagen.id3._frames import APIC, COMM, TALB, TBPM, TDRC, TDRL, TIT2, TKEY, TPE1, TPE2, TRCK, TSO2, TYER, TextFrame
from PIL import Image

from neuro import IMAGES_COVERS_DIR, IMAGES_CUSTOM_DIR, LOG_DIR, ROOT_DIR
from neuro.utils import file_check, format_logger, SongEntry, sanitize_filename

import polars as pl
from neuro.polars_utils import load_db

from metadata_utils import engraver as engraver


# Lazily-built {album: track count} map, computed once per loaded songs DB.
_counts_source: pl.DataFrame | None = None
_album_track_counts: dict[str, int] | None = None


def get_album_track_count(album: str) -> int:
    """Total number of tracks in `album`.

    The {album: count} map is computed once per loaded songs DB via a single group-by
    (instead of filtering the whole frame on every call), and reused across all songs.
    It's rebuilt automatically when load_db() returns a fresh DataFrame (file changed).

    Args:
        album (str): Album name to look up.

    Returns:
        int: Number of songs sharing that album (0 if it isn't in the DB).
    """
    global _counts_source, _album_track_counts
    df = load_db()
    if _album_track_counts is None or _counts_source is not df:
        grouped = df.group_by("Album").agg(pl.len().alias("count"))
        _album_track_counts = dict(zip(grouped.get_column("Album"), grouped.get_column("count")))
        _counts_source = df
    return _album_track_counts.get(album, 0)


class Song:
    """Represents a Song's Metadata. Abstract class, used for common code between drive/custom songs."""

    @dataclass
    class Flags:
        v1: bool
        """Neuro v1 voice"""
        v2: bool
        """Neuro v2 voice"""
        v3: bool
        """Neuro/Evil v3 voice"""
        neuro: bool
        evil: bool
        duet: bool
        duplicate: bool
        """Duplicate song, file doesn't exist in drive, but song was sung that day"""
        as_drive: bool
        """Use the same naming convention as drive files for filename"""
        as_custom: bool
        """Use the same naming convention as custom files for filename"""
        arg: bool
        """Songs from the ARG channel"""
        official: bool
        originals: bool
        """Songs that have been officially released on at least one streaming service (excluding youtube, because appearently chinatown blues mv version is now included in unofficial archive)"""
        encore: bool
        """Songs that were re-run during the same stream"""
        copyright_issues: bool

    def init_flags(self, flags: str | None) -> None:
        """Detects song's flags by searching substrings in the flags column.\
            Stores the result in `self.flags`.

        Args:
            flags (str | None): Content of the flags column
        """

        # flag is false if song has no flags of if it has flags but not the selected one
        def flag_check(flag: str, flag_field: str | None) -> bool:
            if flag_field is None:
                return False
            flag_list = flag_field.split(";")
            return flag in flag_list

        # Strange code, but just expands into `"v1": flags_check("v1", flags)`...
        # for all flags. It uses the fact that Flags fields are exactly the same
        # strings as the flags
        self.flags = self.Flags(**{flag: flag_check(flag, flags) for flag in self.Flags.__dataclass_fields__.keys()})

    def __init__(self, song_dict: SongEntry, karaoke_dict: dict = {}) -> None:
        # Lots of asserts, mainly for type checking, but also detects irregular entries in database
        assert song_dict["Title"] is not None
        self.title: str = song_dict["Title"]
        self.title_og: str = song_dict["TitleOG"]

        self.identify: str = song_dict["Identify"]

        assert song_dict["Artist"] is not None
        self.artist: str = song_dict["Artist"]
        self.artist_og: str = song_dict["ArtistOG"]

        assert song_dict["Cover Artist"] is not None
        self.cover_artist: str = song_dict["Cover Artist"]

        assert song_dict["Version"] is not None
        self.version: str = song_dict['Version']

        self.comment: str = song_dict['Comment']

        self.special: str = song_dict['Special']

        assert song_dict["Hash_IN"] is not None
        self.hash_in: str = song_dict["Hash_IN"]

        # assert song_dict["File_IN"] is not None
        self.file: Path = ROOT_DIR / Path(song_dict["File_IN"])
        try:
            file_check(self.file)
        except FileNotFoundError:
            # Missing input files are reported and handled in one place, at generation time (neuro/run.py),
            # based on the audio hash map. The library must not exit() from a constructor.
            logger.debug(f"[SONG] Input file missing for '{self.title}': {self.file}")

        assert song_dict["Album_ID"] is not None
        self.track_n: str = song_dict["Album_ID"]

        assert song_dict["Date"] is not None
        self.date: str = song_dict["Date"]

        assert song_dict["Album"] is not None
        self.album: str = song_dict["Album"]

        self.key = song_dict["Key"]  # Can be None
        self.tempo = song_dict["Tempo (1/4 beat)"]  # Can be None

        self.image: str | None = song_dict["Image"]
        self.outfile: Path | None = None

        self.lead_singer = str(song_dict["Lead Singer"]).lower()

        self.d: SongEntry = song_dict
        self.k: SongEntry = karaoke_dict

        self.init_flags(song_dict["Flags"])

    def create_out_file(self, *, out_dir: Path, create: bool = True) -> bool:
        """Virtual method"""
        raise NotImplementedError

    def create_placeholder_files(self, *, out_dir: Path, create: bool = True, numberedFiles: bool = False) -> bool:
        """Creates placeholder files (metadata + cover) in the output directory.

        Args:
            out_dir: Output directory.
            create: If False and the directory already exists, skip.
            numberedFiles: Passed to file_name.

        Returns:
            True if files were created, False if skipped.
        """
        name = self.file_name(self._file_name_custom, numberedFiles=numberedFiles)
        dir_path = out_dir / name

        if not create and dir_path.exists():
            return False

        dir_path.mkdir(parents=True, exist_ok=True)

        metadata_file = dir_path / "metadata.txt"
        metadata_content = (
            f"Title: {self.title}\n"
            f"Title (OG): {self.title_og}\n"
            f"Artist: {self.artist}\n"
            f"Artist (OG): {self.artist_og}\n"
            f"Cover Artist: {self.cover_artist}\n"
            f"Version: {self.version}\n"
            f"Album: {self.album}\n"
            f"Date: {self.date}\n"
            f"Track: {self.track_n}\n"
            f"Identify: {self.identify}\n"
            f"Key: {self.key or 'N/A'}\n"
            f"Tempo: {self.tempo or 'N/A'}\n"
            f"Comment: {self.comment}\n"
            f"Special: {self.special}\n"
            f"Hash: {self.hash_in}\n"
            f"Flags: {self.d.get('Flags', 'N/A')}\n"
            f"Lead Singer: {self.lead_singer}\n"
        )
        metadata_file.write_text(metadata_content)

        # Copy cover image to folder (skip for custom songs with as_drive flag and no image)
        cover = None if (self.image is None and self.flags.as_drive) else self.cover_path
        if cover and cover.exists():
            shutil.copy2(cover, dir_path / "cover.jpg")

        return True

    def create_file_link(self, *, out_dir: Path, existing_path: Path, create: bool = True, numberedFiles: bool = False) -> bool:
        """Creates a filesystem symlink from self.outfile to an existing file.

        Args:
            out_dir: Output directory (same as create_out_file).
            existing_path: Path to the existing file to link to.
            create: If False and self.outfile already exists, skip.
            numberedFiles: Passed to file_name (same as create_out_file).

        Returns:
            True if the link was created, False if skipped.
        """
        self.outfile = self._resolve_outfile(out_dir, numberedFiles)

        full_existing_path = Path.cwd() / existing_path

        if not full_existing_path.exists():
            logger.error(f"file does not exist {full_existing_path}")
            exit(1)

        if not create and self.outfile.exists():
            return False

        if self.outfile.exists() or self.outfile.is_symlink():
            self.outfile.unlink()
        self.outfile.symlink_to(full_existing_path)
        return True

    def apply_tags(self, ascii_tags: bool = False) -> None:
        """virtual method"""
        raise NotImplementedError

    def id3_pic(self, cover: Path) -> APIC:
        """Creates a Cover picture from a given image for files using ID3 tags.

        Args:
            cover (Path): Path to the image used for cover. File must exist (not checked in function).

        Returns:
            APIC: Mutagen APIC type picture to be stored in ID3 tags.
        """
        img = APIC(
            encoding=3,  # 3 is for utf-8
            mime="image/jpeg",  # image/jpeg or image/png
            type=18,  # 3 is for the cover image
            desc="Cover",
            data=cover.read_bytes(),  # read_bytes() closes the handle automatically (open().read() leaked it)
        )
        return img

    def apply_album_artist_and_cover(self, id3: ID3, album_artist: str, cover: Path) -> None:
        """Adds the album-artist (TPE2/TSO2) and cover picture (APIC) frames to an existing ID3 object.
        Shared by `DriveSong.apply_tags` and `CustomSong.apply_id3` so both keep the same frame sequence.

        Args:
            id3 (ID3): Tag object the frames are added to.
            album_artist (str): Value used for both TPE2 and TSO2.
            cover (Path): Cover image path (must exist; not checked here).
        """
        id3.add(TPE2(encoding=3, text=album_artist))
        id3.add(TSO2(encoding=3, text=album_artist))
        # Replaces any picture already present with this song's cover.
        id3.delall("APIC")
        id3.add(self.id3_pic(cover))

    def get_id3_frames(self, ascii_tags: bool = False) -> list[TextFrame]:
        """Gets tags specific to ID3 tags.

        Returns:
            _ (list[TextFrame]): Dictionary with Album artist.
        """
        additional = [
            # Title
            TIT2(text=f"{(self.title if ascii_tags or self.title_og == "None" else self.title_og)}{f" ({self.identify})" if self.identify != "None" else ""}", encoding=3),
            # Artist
            TPE1(text=(f"{self.cover_artist} - {(self.artist if ascii_tags or self.artist_og == "None" else self.artist_og)}" if not (self.flags.originals or self.flags.official) else self.cover_artist), encoding=3),
            # Album
            TALB(text=self.album, encoding=3),
            # Year-Month-Day | Using all frames for different software compatibility
            TDRL(text=self.date, encoding=3),
            TYER(text=self.date[:4], encoding=3),
            TDRC(text=self.date, encoding=3),
            # Track number
            TRCK(text=f"{self.track_n}/{self.album_track_count}", encoding=3),
        ]

        if self.key is not None:
            # Initial key tag
            additional.append(TKEY(text=self.key, encoding=3))
        if self.tempo is not None:
            # Tempo tag
            additional.append(TBPM(text=str(self.tempo), encoding=3))
        return additional

    def get_vorbis_frames(self, ascii_tags: bool = False) -> dict[str, str]:
        """Gets tags specific to Vorbis comments.

        Returns:
            dict[str, str]: Dictionary with Album artist.
        """
        additional = {
            "ALBUM": self.album,
            "ARTIST": (self.artist if not ascii_tags else self.artist_og),
            "DATE": self.date,
            "TITLE": (self.title if not ascii_tags else self.title_og),
            "TRACKNUMBER": f"{self.track_n}",
            "PERFORMER": "Neuro-Sama/Evil Neuro",
        }
        return additional

    @property
    def who(self) -> str:
        """Name used in the dated-cover filename suffix (previously assigned imperatively in apply_tags).

        Returns:
            str: "evil", "neuro" or the subclass-specific fallback (see `_who_fallback`).
        """
        if self.flags.evil:
            return "evil"
        if self.flags.neuro:
            return "neuro"
        return self._who_fallback

    @property
    def _who_fallback(self) -> str:
        """Fallback for `who` when the song has neither an evil nor a neuro flag. Subclass-specific."""
        raise NotImplementedError

    @property
    def cover_path(self) -> Path:
        """Resolved path to the cover image for this song.

        Returns:
            Path: The cover image path (custom image or dated cover).
        """
        if self.image is not None:
            return IMAGES_CUSTOM_DIR / f"{self.image}.jpg"
        if self.flags.duet:
            return IMAGES_COVERS_DIR / f"{self.date}-{self.who}-duet.jpg"
        if self.flags.v1 or self.flags.v2:
            return IMAGES_COVERS_DIR / f"{self.date}.jpg"
        return IMAGES_COVERS_DIR / f"{self.date}-{self.who}.jpg"

    @property
    def album_track_count(self) -> int:
        """Total number of tracks in this song's album (O(1) lookup into a precomputed map).

        Returns:
            int: The number of songs sharing the same album.
        """
        return get_album_track_count(self.album)

    @property
    def _file_name_custom(self) -> bool:
        """Whether file_name() should use custom naming mode. Must be implemented by subclasses."""
        raise NotImplementedError

    def _resolve_outfile(self, out_dir: Path, numberedFiles: bool = False) -> Path:
        """Resolves the output file path. Must be implemented by subclasses."""
        raise NotImplementedError

    @property
    def album_artist(self) -> str:
        """Album artist for karaokes. Defined it as a property for consistency with other attributes.

        Returns:
            str: The artist. Can be Neuro-Sama, Evil Neuro, or Neuro [v1]/[v2].
        """
        # removed the different cases so that all tracks in an album will have the same album_artist,
        if self.flags.v1 and self.date < "2023-05-27":
            return "Neuro [v1]"
        if self.flags.v2 and self.date <= "2023-06-08" and self.cover_artist == "Neuro [v2]":
            return "Neuro [v2]"
        return "Neuro-Sama/Evil Neuro"

    @property
    def name_tag(self) -> str:
        """Name tag to be put in brackets in the file name. Defined it as a property for consistency with\
            other attributes.

        Raises:
            ValueError: When a song doesn't have at least neuro or evil tag.

        Returns:
            str: The tag: Neuro, Evil, Duet, Neuro + Vedal, Neuro v1/v2.
        """
        if self.flags.v1:
            return "Neuro v1"
        if self.flags.v2:
            return "Neuro v2"
        if self.title == "Chinatown Blues":
            return "Neuro + Vedal"
        # A song can have both evil/neuro and duet tags, but the duet tag is prioritized
        if self.flags.duet:
            return "Duet"
        if self.flags.evil:
            return "Evil"
        if self.flags.neuro:
            return "Neuro"
        # A song must have the Neuro or Evil tag, if it has neither, raise an Error
        logger.error(f"Song '{self.file}' has no flags to define its tag!")
        raise ValueError(f"Song '{self.file}' has no flags to define its tag!")

    def file_name(self, custom: bool, numberedFiles: bool = False) -> str:
        """Returns the output filename using song properties.

        Args:
            custom (bool): Use the drive or custom format. **Warning**: A custom song can use the drive\
                format if it has the `as_drive` flag, same for a drive song with `as_custom`.

        Returns:
            str: The filename without type extension.
        """
        # Fragments shared by every naming variant (composed once instead of repeated inline).
        prefix = f"{self.track_n}. " if numberedFiles else ""
        identify = f" ({self.identify})" if self.identify != "None" else ""
        encore = " - Encore" if self.flags.encore else ""

        # originals and official use the exact same format, so a single branch covers both.
        if custom and (self.flags.originals or self.flags.official):
            filename = f"{prefix}{self.cover_artist} - {self.title}{identify}{encore}"
        elif custom and not self.flags.originals:
            filename = f"{prefix}{self.artist} - {self.title}{identify}{encore} - {self.cover_artist}"
        else:
            filename = f"{prefix}{self.artist} - {self.title}{identify}{encore} [{self.name_tag}] [{self.date}]"
        # TODO add {self.track_n} to start of file name
        # TODO get total number of tracks for tag
        # TODO if entire karaoke stream (only karaoke streams, not the subathon or other setlists from the non-karaoke folder)
        #       if entire stream is duets, remove the 'neuro;' or 'evil;' flags

        return sanitize_filename(filename)

class DriveSong(Song):
    """Metadata for a song from the drive."""

    def __init__(self, song_dict: dict, karaoke_dict: dict) -> None:
        super().__init__(song_dict, karaoke_dict)

    @property
    def _file_name_custom(self) -> bool:
        return self.flags.as_custom

    @property
    def _who_fallback(self) -> str:
        return self.lead_singer

    def _resolve_outfile(self, out_dir: Path, numberedFiles: bool = False) -> Path:
        name = self.file_name(self._file_name_custom, numberedFiles=numberedFiles)
        return ROOT_DIR / out_dir / f"{name}.mp3"

    def create_out_file(self, *, out_dir: Path = Path("out"), create: bool = True, numberedFiles: bool = False) -> bool:
        """Creates the output file on the filesystem by copying the original. The metadata are written later.

        Args:
            out_dir (Path, optional): Output directory. Should be defined in the config file. \
                Defaults to Path("out").
            create (bool, optional): Force to create a copy of the file even if a file already exists. \
                Defaults to True.

        Returns:
            bool: True if a file was created.
        """
        # Ensures the output directory exists
        os.makedirs(ROOT_DIR / out_dir, exist_ok=True)
        # If the song is flagged as custom, use the custom format
        name = self.file_name(self.flags.as_custom, numberedFiles=numberedFiles)
        self.outfile = ROOT_DIR / out_dir / f"{name}.mp3"

        # print(self.file)
        # print(self.outfile)

        if create or (not self.outfile.exists()):
            shutil.copy2(self.file, self.outfile)
            return True
        return False

    def apply_tags(self, ascii_tags: bool = False) -> None:
        """Applies ID3 tags on the file. First uses EasyID3 for text tags. Then ID3 to write the cover
        picture to the file.
        """
        # Text tags
        id3 = ID3(self.outfile)

        common_props = self.get_id3_frames(ascii_tags=ascii_tags)
        for frame in common_props:
            id3.add(frame)


        track_n = f"{self.track_n}/{self.album_track_count}"

        # Cover Image (self.who is now computed on demand by the cover_path property)
        cover = self.cover_path
        file_check(cover)

        self.apply_album_artist_and_cover(id3, self.album_artist, cover)

        # Add the JSON metadata payload to this same ID3 object and save once,
        # instead of engrave_payload() re-parsing and re-saving the whole file.
        payload_data = engraver.build_payload(self.file, self.date, self.title, self.title_og,
                               self.identify, self.artist, self.artist_og,
                               self.cover_artist, self.version, self.album, "1", track_n,
                               self.comment, self.special, self.hash_in)
        id3.add(COMM(encoding=3, lang="ved", desc="", text=[payload_data]))
        id3.save(v2_version="3", v1="2")


class CustomSong(Song):
    """Metadata for a song added manually (not from the drive)."""

    def __init__(self, song_dict: dict, karaoke_dict: dict = {}) -> None:
        super().__init__(song_dict, karaoke_dict)

    @property
    def _who_fallback(self) -> str:
        return "twins"

    @property
    def _file_name_custom(self) -> bool:
        return not self.flags.as_drive

    def _resolve_outfile(self, out_dir: Path, numberedFiles: bool = False) -> Path:
        name = self.file_name(self._file_name_custom, numberedFiles=numberedFiles)
        return ROOT_DIR / out_dir / f"{name}{self.file.suffix}"

    def create_out_file(self, *, out_dir: Path, create: bool = True, numberedFiles: bool = False) -> bool:
        """Creates the output file on the filesystem by copying the original. The metadata are written later.

        Args:
            out_dir (Path, optional): Output directory. Should be defined in the config file. \
                Defaults to Path("out").
            create (bool, optional): Force to create a copy of the file even if a file already exists. \
                Defaults to True.
        Returns:
            bool: True if a file was created.
        """
        file = self.file
        ext = file.suffix

        name = self.file_name(not self.flags.as_drive, numberedFiles=numberedFiles)
        self.outfile = ROOT_DIR / out_dir / f"{name}{ext}"

        if create or (not self.outfile.exists()):
            shutil.copy2(file, self.outfile)
            return True
        return False

    def apply_tags(self, ascii_tags: bool = False) -> None:
        """Custom Song version of the tag management. Here it needs to check the file's format first\
            to apply the right type of tag.

        Raises:
            ValueError: If the file isn't a .mp3 or .flac file.
        """
        ext = self.file.suffix
        # print(self.file)
        # print(self.flags)
        if self.image is None and not self.flags.as_drive:
            logger.error(f"Image can't be None for custom song {self.file}")

        # Cover Image (self.who is now computed on demand by the cover_path property)
        self.cover = self.cover_path
        file_check(self.cover)

        match ext:
            case ".mp3":
                self.apply_id3(ascii_tags=ascii_tags)
            case ".flac":
                self.apply_tags_vorbis()
            case _:
                logger.error(f"Unimplemented file suffix for {self.file}")
                raise ValueError(f"Unimplemented file suffix for {self.file}")

    def apply_id3(self, ascii_tags: bool = False) -> None:
        """ID3 version of the metadata management. Similar to the one for Drive Songs."""
        id3 = ID3(self.outfile)
        id3.delete()

        for frame in self.get_id3_frames(ascii_tags=ascii_tags):
            id3.add(frame)

        track_n = f"{self.track_n}/{self.album_track_count}"

        if self.flags.as_drive or self.flags.arg:
            album_artist = self.album_artist
        else:
            album_artist = "Neuro-Sama/Evil Neuro"

        # Album artist (TPE2/TSO2) + cover picture (APIC), same shared sequence as DriveSong.
        self.apply_album_artist_and_cover(id3, album_artist, self.cover)

        # Add the JSON metadata payload to this same ID3 object and save once,
        # instead of engrave_payload() re-parsing and re-saving the whole file.
        payload_data = engraver.build_payload(self.file, self.date, self.title, self.title_og,
                               self.identify, self.artist, self.artist_og,
                               self.cover_artist, self.version, self.album, "1", track_n,
                               self.comment, self.special, self.hash_in)
        id3.add(COMM(encoding=3, lang="ved", desc="", text=[payload_data]))
        id3.save(v2_version="3", v1="2")

    def get_flac_pic(self) -> Picture:
        """Generates a picture for a FLAC file's cover. This very particular method works, so\
            I won't modify it without a valid reason.

        Returns:
            Picture: The encoded cover picture.
        """
        img = Image.open(self.cover)
        if img.mode == "RGBA":
            img = img.convert("RGB")

        buffer = BytesIO()
        img.save(
            buffer,
            format="JPEG",
            quality=85,
            optimize=True,
            progressive=False,
        )
        image_file = buffer.getvalue()
        img.close()

        image = Picture()
        image.type = 3
        image.mime = "image/jpeg"
        image.desc = "Cover"
        image.data = image_file
        return image

    def apply_tags_vorbis(self, ascii_tags: bool = False) -> None:
        """FLAC specific tag handling (for 2 files atm...).

        Raises:
            ValueError: If the file has no tag header present.
        """
        # Based on https://exiftool.org/TagNames/Vorbis.html tags descriptions
        file = FLAC(self.outfile)
        if file.tags is None:
            logger.error(f"File {self.file} has no tags header.")
            raise ValueError

        common = self.get_vorbis_frames(ascii_tags=ascii_tags)
        for k, v in common.items():
            # Uppercase totaly unneeded I think
            file.tags[k.upper()] = v  # type: ignore

        # Cover
        image = self.get_flac_pic()

        file.clear_pictures()
        file.add_picture(image)
        file.save()


if __name__ == "__main__":
    format_logger(log_file=LOG_DIR / "tags.log")
