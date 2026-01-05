"""Thumbnail generation for the songs"""

import os
from pathlib import Path
from string import digits
from time import time
from typing import Literal, TypeAlias

import PIL.Image as Image
import polars as pl
from loguru import logger

from neuro import (
    DATES_OLD_CSV,
    IMAGES_BG_DIR,
    IMAGES_COVERS_DIR,
    IMAGES_CUSTOM_DIR,
    IMAGES_DATES_DIR,
    LOG_DIR,
)
from neuro.polars_utils import load_dates
from neuro.utils import format_logger, time_format

# 01 19 296 
# 02 06 310
# 03 03 312
# 04 02 313
# 05 06 309
# 06 01 314
# 07 07 308
# 08 02 313
# 09 03 312
# 10 19 296
# 11 39 276
# 12 25 290


DATES_MONTH_BOUND_BOX_SIZES = [
    [19, 296],
    [6, 310],
    [3, 312],
    [2, 313],
    [6, 309],
    [1, 314],
    [7, 308],
    [2, 313],
    [3, 312],
    [19, 296],
    [39, 276],
    [25, 290]
]

# DATES_DAY_BOUND_BOX_SIZES = []

# TODO figure out why the day numbers don't line up properly vertically (seriously, what is going on, why don't they match the spacing of the year and month)
# TODO make a lookup table for day bounding box dimensions
# TODO figure out how to space characters to mimic proper kerning
# TODO move this function and related changes to a seperate branch, merge that branch into main, then merge main back into unofficialV3_extract
def apply_text_from_date_atlases(image: Image.Image,
                                 year: int,
                                 month: int,
                                 day: int,
                                 MAX_SIZE: int = 500
) -> Image.Image:
    """Writes a date from new Year, Month, and Day text atlas images on an image. Resizes the\
       image to fit in a MAX_SIZExMAX_SIZE (default 500) Square. Returns the modified image.
       
    Args:
        image (ImageFile): Background Image
        year (int): the year part of the date - 2023 - 2026
        month (int): the month part of the date - 1 - 12
        day (int): the day part of the date - 1 - 31
            does not check if date is valid
            
    Returns:
            Image.Image: Image with the date text pasted on it."""
    years = Image.open(IMAGES_DATES_DIR / "text_atlas_year.png").convert("RGBA")
    months = Image.open(IMAGES_DATES_DIR / "text_atlas_month.png").convert("RGBA")
    days = Image.open(IMAGES_DATES_DIR / "text_atlas_day.png").convert("RGBA")

    year_w = years.width
    month_w = DATES_MONTH_BOUND_BOX_SIZES[month-1][1] - DATES_MONTH_BOUND_BOX_SIZES[month-1][0]
    day_w = days.width

    date_w = year_w + month_w + day_w
    date_h = 170

    year_idx = year - 2023
    month_idx = month - 1
    day_idx = day - 1
    
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

    # Cropping the Date zone in the dates atlas
    year_box_up = date_h * year_idx
    year_box_down = year_box_up + date_h

    month_box_up = date_h * month_idx
    month_box_down = month_box_up + date_h

    day_box_up = date_h * day_idx
    day_box_down = day_box_up + date_h

    year_zone = (0,year_box_up, year_w, year_box_down)
    year_crop = years.crop(year_zone)

    month_zone = (DATES_MONTH_BOUND_BOX_SIZES[month-1][0], month_box_up, DATES_MONTH_BOUND_BOX_SIZES[month-1][1], month_box_down)
    month_crop = months.crop(month_zone)

    day_zone = (0, day_box_up, day_w, day_box_down)
    day_crop = days.crop(day_zone)

    # Scaling text to image
    TEXT_RATIO = 0.6
    text_w = TEXT_RATIO * w
    text_h = text_w * date_h / date_w # Keeps the text aspect ratio
    # th = tw * dh / dw
    # th * dw = tw * dh
    # th * dw / dh = tw
    year_resize_w = text_h * year_w / date_h
    month_resize_w = text_h * month_w / date_h
    day_resize_w = text_h * day_w / date_h
    
    year_text = year_crop.resize([int(year_resize_w), int(text_h)])
    month_text = month_crop.resize([int(month_resize_w), int(text_h)])
    day_text = day_crop.resize([int(day_resize_w), int(text_h)])

    # Pastes the date onto the original image
    text_x = int((w - text_w) / 2)
    text_y = int(0.8 * h)

    year_x = int(text_x)
    month_x = int(year_x + year_resize_w)
    day_x = int(month_x + month_resize_w)

    year_paste_zone = (year_x, text_y)
    month_paste_zone = (month_x, text_y)
    day_paste_zone = (day_x, text_y)

    # Pastes the date onto the original image
    new_image.paste(year_text, year_paste_zone, year_text)
    new_image.paste(month_text, month_paste_zone, month_text)
    new_image.paste(day_text, day_paste_zone, day_text)

    return new_image


def apply_text(
    image: Image.Image,
    dates: Image.Image,
    date_idx: int,
    *,
    date_w: int = 900,
    date_h: int = 170,
    OFFSET: int = 15,
    MAX_SIZE: int = 500,
) -> Image.Image:
    """Writes a date from a text atlas image on an image. Resizes the image to fit in a \
        MAX_SIZExMAX_SIZE (default 500) square. Returns the modified image to avoid in-place\
        modification of the image.

    Args:
        image (ImageFile): Background image
        dates (ImageFile): Image atlas containing all dates, assumes the dates\
            image is an atlas where each date text is 900x183 px (or else, but \
            defined in date_w and date_h)
        date_idx (int): Index of the date in the atlas, starts at 0
        date_w (int, optional): Width of the date image.\
            Defaults to 900.
        date_h (int, optional): Height of one date entry. \
            Defaults to 170.
        OFFSET (int, optional): Offset before the start of the first date. \
            Defaults to 15.
        MAX_SIZE (int, optional): Maximum size for a cover (one dimension \
            given, aspect ratio is preserved). \
            Defaults to 500.

    Returns:
            Image.Image: Image with the text pasted on it.
    """
    w, h = image.size
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

    # Cropping the Date zone in the dates atlas
    # TODO: One day use a less scuffed way to do that (but still have a good looking text outline)
    box_up = OFFSET + date_h * date_idx
    box_down = box_up + date_h
    # Crop zone, order: Left, Up, Right, Down
    zone = (0, box_up, date_w, box_down)
    date_crop = dates.crop(zone)

    # Scaling text to image
    TEXT_RATIO = 0.6
    text_w = TEXT_RATIO * w
    text_h = text_w * date_h / date_w  # Keeps the text aspect ratio
    date_text = date_crop.resize([int(text_w), int(text_h)])

    # Pastes the date onto the original image
    text_x = int((w - text_w) / 2)
    text_y = int(0.8 * h)

    paste_zone = (text_x, text_y)
    new_image.paste(date_text, paste_zone, date_text)

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
    format_logger(log_file=LOG_DIR / "thumbnails.log")
    t = time()
    # v1 | v2
    SOLO_BG = list(map(lambda name: open_image(IMAGES_BG_DIR, name), ["nuero.png", "nwero_v2.png"]))

    dates = pl.read_csv(DATES_OLD_CSV)
    N_COVERS = len(dates)
    os.makedirs(IMAGES_COVERS_DIR, exist_ok=True)
    os.makedirs(IMAGES_CUSTOM_DIR, exist_ok=True)

    DATES_MONTHS = Image.open(IMAGES_DATES_DIR / "2023-dates-months.png").convert("RGBA")
    DATES_KARAOKES = Image.open(IMAGES_DATES_DIR / "2023-dates-v12.png").convert("RGBA")
    i_m, i_k = 0, 0
    for stream in dates.iter_rows(named=True):
        date: str = stream["Date"]
        ver: str = stream["Voice"]
        if ver == "v1":
            base = SOLO_BG[0]
        else:
            base = SOLO_BG[1]


        if date[5] in digits:  # It's a month digit and not a month written in letters
            date_img = DATES_KARAOKES        
            year = 2023
            month = digits.find(date[5]) * 10 + digits.find(date[6])
            day = digits.find(date[8]) * 10 + digits.find(date[9])
            apply_text_from_date_atlases(base, year, month, day).convert("RGB").save(IMAGES_COVERS_DIR / f"{date}.jpg")
            i_k += 1
        else:
            date_img = DATES_MONTHS
            # Use custom sized dates because months letters make them bigger
            apply_text(
                base,
                date_img,
                i_m,
                date_w=1250,
                date_h=215,
            ).convert("RGB").save(IMAGES_CUSTOM_DIR / f"{date}.jpg")
            i_m += 1

        index = i_m + i_k - 1
        logger.debug(f"[THUMB] [{index + 1:2d}/{N_COVERS}] Cover Pictures for {date} done")

    logger.success(f"[THUMB] {N_COVERS} successfully generated in {time_format(time() - t)}")


def check_stream(stream: dict[str, str]) -> None:
    """Checks if the data matches the expectations

    Args:
        stream (dict[str, str]): Row from the dates csv

    Raises:
        ValueError: If one of these conditions isn't fulfilled:
        - year isn't in [2023, 2024]
        - Singer isn't Neuro or Evil
        - Duet format isn't v1, v2v1 or v2
    """
    year = stream["Date"][:4]
    if year not in ["2023", "2024", "2025", "2026"]:
        raise ValueError(f"Wrong year {year}")

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
    format_logger(log_file=LOG_DIR / "thumbnails.log")

    # fmt: off
    # v3 | v3 Voice w/ v2 Model | Eliv v1 Model | Eliv v2 Model
    SOLO_BG = list(map(
        lambda name: open_image(IMAGES_BG_DIR, name),
        ["nwero.png", "newero.png", "eliv.png", "neweliv.png"],
    ))

    # Neuro v2, Evil v1 | Neuro v3, Evil v1 | Neuro v3, Evil v2
    DUET_BG = list(map(
        lambda name: open_image(IMAGES_BG_DIR, name),
        ["smocus.jpg", "smocus_inter.png", "smocus_new.png"],
    ))

    DATES_IMAGES = {
        y: open_image(IMAGES_DATES_DIR, f"{y}-dates.png", rgba=True)
        for y in range(2023, 7)
    }
    # fmt: on

    logger.info("[THUMB] Starting the generation of thumbnails")

    t = time()
    dates = load_dates()

    N_COVERS = len(dates)

    os.makedirs(IMAGES_COVERS_DIR, exist_ok=True)
    # Indices keeping track for 2023 | 2024 | 2025 | 2026 images
    indices = {y: 0 for y in range(2023, 2027)}

    for stream in dates.iter_rows(named=True):
        check_stream(stream)
        date = stream["Date"]
        who = stream["Singer"]
        version = stream["Duet Format"]

        year = int(date[:4])
        date_idx = indices[year]
        indices[year] += 1

        print(who)

        i_solo, i_duet = singer_match(who, version)

        # Doesn't generate solo covers for Twins streams
        if i_solo != -1:
            # Solo thumbnail generation
            month = digits.find(date[5]) * 10 + digits.find(date[6])
            day = digits.find(date[8]) * 10 + digits.find(date[9])
            apply_text_from_date_atlases(SOLO_BG[i_solo], year, month, day).convert("RGB").save(IMAGES_COVERS_DIR / f"{date}-{str(who).lower()}.jpg")
        # Duet thumbnail generation
        month = digits.find(date[5]) * 10 + digits.find(date[6])
        day = digits.find(date[8]) * 10 + digits.find(date[9])
        apply_text_from_date_atlases(DUET_BG[i_duet], year, month, day).convert("RGB").save(IMAGES_COVERS_DIR / f"{date}-{str(who).lower()}-duet.jpg")

        print(IMAGES_COVERS_DIR / f"{date}-{str(who).lower()}.jpg")
        print(IMAGES_COVERS_DIR / f"{date}-{str(who).lower()}-duet.jpg")

        

        i_total = sum(indices.values()) - 1
        logger.debug(f"[THUMB] [{i_total + 1:2d}/{N_COVERS}] Cover Pictures for {date} done")

    logger.success(f"[THUMB] {N_COVERS} successfully generated in {time_format(time() - t)}")


if __name__ == "__main__":
    generate_main()
