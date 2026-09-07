"""Thumbnail generation for the songs"""

import os
from pathlib import Path
from string import digits
from time import time

import polars as pl
from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from . import DATES_OLD_CSV, FONT_PATH, LOG_DIR, get_project
from .artists import Project
from .cli import chdir_to_project
from .polars_utils import load_dates
from .utils import format_logger, time_format


def apply_text(image: Image.Image,
                        text: str,
                        font_file: str | Path = Path(FONT_PATH),
                        font_size: int = 64,
                        font_fill_color = (255, 241, 242),
                        font_stroke_width: int = 2,
                        font_stroke_color = (100, 41, 43),
                        MAX_SIZE: int = 500
) -> Image.Image:
    """
    Draw the given text on the image
    """
    w,h = image.size
    new_image = image.copy()

    # Force cover to be at most MAX_SIZExMAX_SIZE (default 500x500)
    if w > MAX_SIZE or h > MAX_SIZE:
        if w == h:  # Case to avoid rounding errors
            new_dims = (MAX_SIZE, MAX_SIZE)
        elif w > h:
            new_dims = (MAX_SIZE, int(MAX_SIZE / w * h))
        else:  # w < h
            new_dims = (int(MAX_SIZE / h * w), MAX_SIZE)
        new_image = new_image.resize(new_dims)
    w, h = new_image.size

    draw = ImageDraw.Draw(new_image)

    try:
        font = ImageFont.truetype(font_file, size=font_size)
    except IOError:
        logger.error("Font \"First Coffee\" not found, exitting...")
        exit(1)

    text_x = int(w / 2)
    text_y = int(h * 0.8)

    draw.text(
        xy = (text_x, text_y),
        text=text,
        font=font,
        fill=font_fill_color,
        anchor="ma",
        stroke_width=font_stroke_width,
        stroke_fill=font_stroke_color
    )

    return new_image

def open_image(folder: Path, name: str, rgba: bool = False) -> Image.Image:
    """Simple wrapper function, mainly to simplify calls in maps."""
    if rgba:
        return Image.open(folder / name).convert("RGBA")
    else:
        return Image.open(folder / name)


def generate_oldge() -> None:
    """Dedicated function to generate v1/v2 voices thumbnails as they shouldn't need to\
        be generated often.\n
        Generates monthly dates in custom folder because that's how they are used.
    """
    chdir_to_project()
    project = get_project()
    format_logger(log_file=LOG_DIR / "thumbnails.log")
    t = time()
    # v1 | v2
    SOLO_BG = list(map(lambda name: open_image(project.images_bg_dir, name), ["nuero.png", "nwero_v2.png"]))

    dates = pl.read_csv(DATES_OLD_CSV)
    N_COVERS = len(dates)
    os.makedirs(project.images_covers_dir, exist_ok=True)
    os.makedirs(project.images_custom_dir, exist_ok=True)

    i_m, i_k = 0, 0
    for stream in dates.iter_rows(named=True):
        date: str = stream["Date"]
        ver: str = stream["Voice"]
        if ver == "v1":
            base = SOLO_BG[0]
        else:
            base = SOLO_BG[1]


        if date[5] in digits:  # It's a month digit and not a month written in letters
            apply_text(base, date).convert("RGB").save(project.images_covers_dir / f"{date}.jpg")
            i_k += 1
        else:
            if date[5] == 'J':
                text = 'January 2023'
            elif date[5] == 'F':
                text = 'Febuary 2023'
            elif date[5] == 'M':
                text = 'March 2023'
            else:
                logger.error(f"How did I get here? neuro.thumbnails.generate_oldge | date == {date} | date[5] == {date[5]}")
                exit(1)
            
            apply_text(base, text).convert("RGB").save(project.images_custom_dir / f"{date}.jpg")
            i_m += 1

        index = i_m + i_k - 1
        logger.debug(f"[THUMB] [{index+1:2d}/{N_COVERS}] Cover Pictures for {date} done")
        # TODO fix calculation of number of cover images to generate

    logger.success(f"[THUMB] [{N_COVERS}/{N_COVERS}] successfully generated in {time_format(time() - t)}")


def check_stream(stream: dict[str, str], project=None) -> None:
    """Checks if the data matches the expectations

    Args:
        stream (dict[str, str]): Row from the dates csv
        project: The active project (defaults to get_project()).

    Raises:
        ValueError: If one of these conditions isn't fulfilled:
        - Singer isn't a project singer or the duet group name
        - Duet format isn't a valid duet version for the project
    """
    if project is None:
        from . import get_project
        project = get_project()
    valid_singers = set(project.singer_names()) | {project.duet_group_name}
    if stream["Singer"] not in valid_singers:
        raise ValueError(f"Wrong singer {stream['Singer']}")

    valid_versions = set((project.bg_duet_images or {}).keys())
    if valid_versions and stream["Duet Format"] not in valid_versions:
        raise ValueError(f"Wrong duet version {stream['Duet Format']}")


def singer_match(singer: str, version: str, project: Project) -> tuple[str | None, str]:
    """Returns (solo_bg_filename, duet_bg_filename) for the given singer and duet version.

    Lookups are driven by the project's ``bg_solo_images`` and ``bg_duet_images`` config,
    so different projects can map singers/versions to different background images.

    Args:
        singer: Singer name (e.g. "Neuro", "Evil") or duet group name (e.g. "Twins").
        version: Duet version string from the dates CSV (e.g. "v1", "v2v1", "v2").
        project: The active project.

    Returns:
        (solo_filename | None, duet_filename): ``solo_filename`` is ``None`` when the singer
        has no solo image for this version (e.g. the duet group).

    Raises:
        ValueError: If no duet bg image is configured for this version.
    """
    solo = (project.bg_solo_images or {}).get(singer, {}).get(version)
    duet = (project.bg_duet_images or {}).get(version)
    if duet is None:
        raise ValueError(
            f"No duet bg image configured for version '{version}' in project '{project.name}' "
            f"([project.thumbnails.duet] in config.toml)"
        )
    return solo, duet

def generate_main() -> None:
    """Generates all thumbnails at once. It automatically re-generate all of them."""
    chdir_to_project()
    project = get_project()
    format_logger(log_file=LOG_DIR / "thumbnails.log")

    if not project.bg_duet_images:
        logger.error(
            f"Project '{project.name}' has no thumbnail bg images configured. "
            f"Add a [project.thumbnails] section to config.toml."
        )
        exit(1)

    # Preload all needed bg images (avoids re-opening files per stream)
    solo_bg: dict[tuple[str, str], Image.Image] = {
        (singer, ver): open_image(project.images_bg_dir, fname)
        for singer, versions in (project.bg_solo_images or {}).items()
        for ver, fname in versions.items()
    }
    duet_bg: dict[str, Image.Image] = {
        ver: open_image(project.images_bg_dir, fname)
        for ver, fname in project.bg_duet_images.items()
    }

    logger.info("[THUMB] Starting the generation of thumbnails")

    t = time()
    dates = load_dates()

    N_COVERS = len(dates)

    os.makedirs(project.images_covers_dir, exist_ok=True)

    i_total = 0

    for stream in dates.iter_rows(named=True):
        check_stream(stream, project)
        date = stream["Date"]

        for who in project.singer_names():  # generate cover images for each project singer
            version = stream["Duet Format"]

            # Solo thumbnail generation (skip for singers with no solo image, e.g. duet group)
            solo_img = solo_bg.get((who, version))
            if solo_img:
                apply_text(solo_img, date).convert("RGB").save(
                    project.images_covers_dir / f"{date}-{who.lower()}.jpg"
                )

            # Duet thumbnail generation
            apply_text(duet_bg[version], date).convert("RGB").save(
                project.images_covers_dir / f"{date}-{who.lower()}-duet.jpg"
            )

        i_total = i_total + 1
        logger.debug(f"[THUMB] [{i_total:3d}/{N_COVERS}] Cover Pictures for {date} done")
        # TODO fix cover art count calculation

    logger.success(f"[THUMB] [{N_COVERS}/{N_COVERS}] successfully generated in {time_format(time() - t)}")


if __name__ == "__main__":
    generate_main()
