"""Thumbnail generation for the songs"""

import os
from pathlib import Path
from string import digits
from time import time
from typing import Literal, TypeAlias

from PIL import Image, ImageDraw, ImageFont

import polars as pl
from loguru import logger

from neuro import DATES_OLD_CSV, LOG_DIR, FONT_PATH
from neuro import get_project
from neuro.polars_utils import load_dates
from neuro.utils import format_logger, time_format

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


def check_stream(stream: dict[str, str]) -> None:
    """Checks if the data matches the expectations

    Args:
        stream (dict[str, str]): Row from the dates csv

    Raises:
        ValueError: If one of these conditions isn't fulfilled:
        - Singer isn't Neuro or Evil
        - Duet format isn't v1, v2v1 or v2
    """
    if stream["Singer"] not in ["Neuro", "Evil", "Twins"]:
        raise ValueError(f"Wrong singer {stream['Singer']}")

    if stream["Duet Format"] not in ["v1", "v2v1", "v2"]:
        raise ValueError(f"Wrong duet version {stream['Duet Format']}")


Singer: TypeAlias = Literal["Neuro", "Evil"]
DuetVersion: TypeAlias = Literal["v1", "v2v1", "v2"]


def singer_match(singer: Singer, version: DuetVersion) -> tuple[int, int]:
    """Returns solo and duet images indices in their lists.

    Args:
        singer (str): Who is singing, should be "Neuro" or "Evil".
        version (str): Version for duets, should be "v1", "v2" or "v1v2".

    Returns:
        solo/duet (tuple[int, int]): Index for solo and duet background images.\
            Solo: 0 for Neuro v2 | 1 for Neuro v3 | 2 for Evil v1 | 3 for Evil v2. | -1 for Twins\
            Duet: 0 for Neuro/Evil v2/v1 | 1 for v3/v1 | 2 for v3/v2.
    """
    match singer:
        case "Neuro":
            solo = 0
            # v2 in version means Neuro v2 was already released
            if "v2" in version:
                solo = 1
        case "Evil":
            solo = 3
            # v1 in version means Evil v2 wasn't already released
            if "v1" in version:
                solo = 2
        case "Twins":
            solo = -1

    match version:
        case "v1":
            duet = 0
        case "v2v1":
            duet = 1
        case "v2":
            duet = 2

    return solo, duet

def generate_main() -> None:
    """Generates all thumbnails at once. It automatically re-generate all of them."""
    project = get_project()
    format_logger(log_file=LOG_DIR / "thumbnails.log")

    # fmt: off
    # v3 | v3 Voice w/ v2 Model | Eliv v1 Model | Eliv v2 Model
    SOLO_BG = list(map(
        lambda name: open_image(project.images_bg_dir, name),
        ["nwero.png", "newero.png", "eliv.png", "neweliv.png"],
    ))

    # Neuro v2, Evil v1 | Neuro v3, Evil v1 | Neuro v3, Evil v2
    DUET_BG = list(map(
        lambda name: open_image(project.images_bg_dir, name),
        ["smocus.jpg", "smocus_inter.png", "smocus_new.png"],
    ))
    # fmt: on

    logger.info("[THUMB] Starting the generation of thumbnails")

    t = time()
    dates = load_dates()

    N_COVERS = len(dates)

    os.makedirs(project.images_covers_dir, exist_ok=True)

    i_total = 0

    for stream in dates.iter_rows(named=True):
        check_stream(stream)
        date = stream["Date"]

        for who in ['Neuro', 'Evil']: # TODO temp fix to generate cover images for both singers for each date
            version = stream["Duet Format"]

            # print(who)

            i_solo, i_duet = singer_match(who, version)

            # Doesn't generate solo covers for Twins streams
            if i_solo != -1:
                # Solo thumbnail generation
                apply_text(SOLO_BG[i_solo], date).convert("RGB").save(project.images_covers_dir / f"{date}-{str(who).lower()}.jpg")
            # Duet thumbnail generation
            apply_text(DUET_BG[i_duet], date).convert("RGB").save(project.images_covers_dir / f"{date}-{str(who).lower()}-duet.jpg")

            # print(project.images_covers_dir / f"{date}-{str(who).lower()}.jpg")
            # print(project.images_covers_dir / f"{date}-{str(who).lower()}-duet.jpg")

        i_total = i_total + 1
        logger.debug(f"[THUMB] [{i_total:3d}/{N_COVERS}] Cover Pictures for {date} done")
        # TODO fix cover art count calculation

    logger.success(f"[THUMB] [{N_COVERS}/{N_COVERS}] successfully generated in {time_format(time() - t)}")


if __name__ == "__main__":
    generate_main()
