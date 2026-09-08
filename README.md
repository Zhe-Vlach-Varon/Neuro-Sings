<div align="center">

![Latest Karaoke](https://img.shields.io/badge/latest-2026--08--19-a)
![Python version](https://img.shields.io/badge/Python-3.12-%23306998?logo=python&labelColor=%23ffd43b)

# Neuro-sing-DB

<div style="display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
    <a href="projects/neuro/images/github/Album-1.png">
        <img src="projects/neuro/images/github/Album-1.png" width=125px alt="Album generated">
    </a>
    <a href="projects/neuro/images/github/Playlist-1.png">
        <img src="projects/neuro/images/github/Playlist-1.png" width=125px alt="Glimpse of the whole laylist">
    </a>
    <a href="projects/neuro/images/github/Song-1.png">
        <img src="projects/neuro/images/github/Song-1.png" width=125px alt="Song generated (LIFE)">
    </a>
    <a href="projects/neuro/images/github/Song-2.png">
        <img src="projects/neuro/images/github/Song-2.png" width=125px alt="Song generated (BOOM)">
    </a>
    <a href="projects/neuro/images/github/Playlist-2.png">
        <img src="projects/neuro/images/github/Playlist-2.png" width=125px alt="Glimpse of the whole laylist">
    </a>
    <a href="projects/neuro/images/github/Album-2.png">
        <img src="projects/neuro/images/github/Album-2.png" width=125px alt="Album generated">
    </a>
</div>

</div>

A project dedicated to creating a database of covers from [Neuro-Sama](https://en.wikipedia.org/wiki/Neuro-sama).
The main goal of this project is to have an easy way to export all covers for offline uses.
The databse aims to provide as much metadata as possible/reasonable for the files to be easily classified by offline music players and provide a nice display thanks to the image covers.

This project has been realised in Python (3.12) with the use of the [PDM package manager](https://pdm-project.org) for python.

## Downloading songs and new batches
On each new karaoke the database needs to be updated.\
Should only be fetching the diffs from my drive.\
I recommand using a tool like [rclone](https://rclone.org/) or any alternative to just download the diff instead or redownloading everything everytime.

### For someone using this project
Wait for me to do all this work and upload it properly (pls be patient, I try to be fast)
I should have put a Google Drive link somewhere with all the files ready to be downloaded. I don't want to put them on GitHub (even the link). I may send them somewhere on Discord.

The Google Drive holds the generated files in the `out/` tree (`unofficial_releases/` and `official_releases/`), each containing the presets (`original_sort/*` and `zvv_sort/*`) plus the `albums/` tree.

It also has an `_inputs` directory; its content can be copied into the root directory of this project to obtain the full input data (`setlists/`, `data/`, `images/`, `custom/`, `unofficialV3/`, the official/copyrighted source audio, `fonts/` and the `.vscode/` config).

### For me (for each batch)
- [x] Get the new song names + order (setlist file in `setlists/`)
- [x] Pull input files `inputs-pull` (setlists, data, images, custom, unofficialV3, etc.)
- [x] Generate json `update-json`
- [x] Sanitize json
  - [x] Check artists name, check coherency with database with queries
  - [x] Set track number
  - [x] ASCII check
- [x] Update the database `update-db` (also runs the setlist↔DB consistency check)
- [x] Check for errors again
- [x] Run all checks `db-check`
- [x] Generate new thumbnails `thumbnails-generate`
- [x] Generate the albums tree `albums-generate`
- [x] Generate songs `songs-generate` (presets symlink to the albums tree)
- [x] Upload the result to the drive `drive-push`
- [x] Post update on Discord
- [x] Profit

*Note*: filenames are sanitized automatically (`ai_vt_singer/utils.py::sanitize_filename` replaces characters that are forbidden/awkward in filenames), so you no longer need to hand-write a sanitized "ASCII" variant of a title/artist in the JSON.

*Another Note*: the setlist for the most recent karaoke is often added **before** the audio files are available in the archive. In that case `update-db` may fail on brand-new songs of that stream (a `duplicate` with no source file anywhere, see `"How did we get here?!"` in `json_to_csv.get_most_recent_version`). That is a data gap, not a code bug: wait for the files and re-run. To test the whole pipeline from scratch use: `clear-db` → `update-json` → `update-db` → `db-check`.

## What are "duplicates"?
Some songs in the database have the "duplicate" flag. But what does it mean?\
It means it is a song that was sung on a given karaoke but has no file corresponding on the drive because it was already sung before.

Since this database sorts covers by albums with one album per karaoke stream with track number for the tracks to be ordered, those missing songs create gaps in numbers.
So even if the audio files are identical, it is possible to generate those "duplicates" using the same files, so the albums will be complete.

## Disclaimers
- I don't have extended knowledge about vocaloids, so if I put a producer or lyricist or singer as the "Artist" it does not mean anyting, I just probably took the name indicated or did some very basic research and put the first name I found as the artist. If a name is more appropriate for a song please tell me.
- This lack of knowledge extends to pretty much all the artists that I don't know that well. So if a title or artist is incorrect, please tell me.
- There may be some exceptions but I don't intend to put all the Japanese titles in kana or kanji.
- You can create flags in the database, but they must be spelled exactly and kept consistent everywhere: the `Flags` column is a semicolon-separated string (e.g. `v3;neuro;` with a trailing separator) and matching is **exact** (the string is split on `;` and each token compared), not substring. So a flag only works if it is spelled correctly and the `;` separator is consistent between the writer (`ai_vt_singer/utils.py::get_flags`) and the readers (`config.toml` presets, `ai_vt_singer/file_tags.py`, `ai_vt_singer/polars_utils.py`).
- There may be instances of DD-MM-YYYY and YYYY-MM-DD dates format in the code, I may someday go through all the code to be more consistent but I'm too lazy for now.
- I do not own any of the images used for covers, I think I've given proper credit in the README file in the `images/` directory. If credit is missing please notify me.


## Scripts
All the scripts can be run with `pdm run <script-name>` after you ran `pdm install`.
#### Generation
- `songs-generate`: Generates all presets of songs. Main script! (When `make-links` is on, it symlinks into the albums tree, so run `albums-generate` first.)
- `songs-generate-group <group>`: Generates only the presets belonging to a single group (see the `group` field in the Presets section). Use `all` to generate everything, or `default` for presets with no explicit group.
- `check-group [group]`: Verifies that a group's presets **partition** the database — every song appears in exactly one preset of the group — and reports any **missing** (in no preset) or **duplicated** (in more than one preset) songs. With no argument (or `all`) it checks every group in the config; otherwise pass a group name (e.g. `zvv_sort`).
- `albums-generate`: Generates the "sorted by album" tree that `songs-generate` links into
- `thumbnails-generate`: Generates all thumbnails with dates
- `thumbnails-old`: Generates the older style of thumbnails
#### New batch
- `inputs-pull`: Pulls all input files (setlists, data, images, custom, unofficialV3, etc.) from my drive (using `rclone`)
- `setlists-pull`: Pulls only the setlists
- `drive-pull`: Pulls the `unofficialV3` audio from the unofficial archive (using `rclone`)
- `update-json`: Searches through all present files for untreated files, fills in setlist duplicates, then adds them to `data/songs_new.json`
- `update-db`: Reads the sanitized JSON, adds new files to the database (CSV + SQLite) and re-indexes, then runs the setlist↔DB consistency check
- `clear-db`: Wipes both databases down to an empty schema (to rebuild from scratch)
- `db-check`: Runs various checks on the database (hashes, casing, mp3gain, CSV↔SQLite equality, setlist match)
- `setlist-check`: Compares the setlists against the DB and reports missing/extra/mismatched entries and flags
- `drive-push`: Pushes locally generated files to my drive (requires write access and having the drive set up with `rclone`)
- `setlists-push`: Pushes the setlists to my drive
#### Others
- `db-sync`: Loads the CSV database (the source of truth) and rewrites both the CSV and DB databases, syncing them
- `mp3gain_standalone`: Runs mp3gain (takes a long time) on the music files, useful for running it after generating a preset where it wasn't applied

## Setup
All this setup assumes a Linux environment, I don't have a Windows environment to test it right now.
### tl;dr (Linux)
[Install pipx](https://pipx.pypa.io/stable/installation/)
```bash
pipx install pdm
pdm install
eval $(pdm venv activate)
```

### More details
1. Use your package manager to install pipx or python-pipx, check [here](https://pipx.pypa.io/stable/installation/).
2. Check if you have python installed, pipx should install it anyways.
3. Install pdm via pipx by typing `pipx install pdm`.
4. On the root of the project run `pdm install` to download the packages and create scripts shortcuts.
5. Activate venv for python `eval $(pdm venv activate)` on linux, see [this part of the documentation](https://pdm-project.org/en/latest/usage/venv/#activate-a-virtualenv)
6. Run the scripts you want. [See this part](#scripts)

### Windows
NOT TESTED

1. Install [scoop.sh](https://scoop.sh/)
2. Use scoop to install pipx and python 3.12 (python312 in versions bucket)
3. Install pdm via pipx
4. The lockfile may be linux-specific, if you encounter any problems, you may delete the lockfile.

## Config file
Each project has its own `config.toml` in its project directory (e.g. `projects/neuro/config.toml`;
the active one is simply the `config.toml` in the directory you run the command from, or the one
named by `--project`). Proper documentation is given in the file.

> [!WARNING]
> The mp3gain features requires to have the [`mp3gain`](https://mp3gain.sourceforge.net) software installed and accessible in your path. Run the `db-check` script to ensure it's working. Otherwise disable the feature.

### Presets
These are the main parts of the config file. A preset defines a selection of files that are generated in a given directory.\
Each preset is defined by the flags to include and to exclude. The preset is defined by all the files that have one of the include flags and has none of the exclude flags.\
You can create as many presets as you want, they can totaly overlap.\
Some examples are commented out.

**Groups** (optional): each preset may declare a `group` field (e.g. `group = "zvv_sort"`). A group does two things:
- It is the **parent directory** for the presets in that group. The preset's `path` is relative to the group, so the final output is `<out-root>/<group>/<path>` (with `use-root`, or `./<group>/<path>` without). So `group = "zvv_sort"` + `path = "Neuro"` → `out/zvv_sort/Neuro`.
- It is an **independent set** you can generate on its own, so you don't have to rebuild every preset when you only changed one collection.

Presets with no `group` keep their `path` as-is (no parent dir) and belong to the implicit `default` group.
- `songs-generate` always generates **every** preset (all groups) — unchanged behavior.
- `songs-generate-group <name>` generates only that group's presets. `<name>` can be a group name (e.g. `zvv_sort`, `original_sort`), `all` (everything), or `default`. It errors and lists the available groups if the name matches nothing.
- Currently the presets are split into two groups, which are also their top-level output folders: `original_sort` and `zvv_sort`.


## Multi-project support

The codebase can manage **multiple independent cover-artist projects** from a single checkout.
Each project is a self-contained directory with its own `config.toml`, database, input files,
and output. This is useful for maintaining separate singer databases (e.g. Neuro Twins + Vedal)
without mixing their data.

### How it works

- **`[project]` config section** (`config.toml`): defines the project's identity — singer
  names, flag tokens, voice versions, duet group name, drive remotes, and all paths.
- **`ai_vt_singer/artists.py`**: `CoverArtist` (one singer) and `Project` (one full project) dataclasses.
- **`ai_vt_singer/config.py`**: `load_project()` parses `config.toml` → `Project` (the config **must** contain a `[project]` section).
- **`ai_vt_singer/__init__.py`**: `get_project()` returns the cached active project.
- **`ai_vt_singer/cli.py`**: `chdir_to_project()` enables the `--project <dir>` flag on all commands.

### Using multiple projects

Each project directory contains its own `config.toml` + `data/` + `songs/` + `setlists/` +
`images/` + `out/`. Two equivalent ways to select which project to operate on:

```bash
# Option 1: cd into the project
cd projects/my-project
pdm run db-check
pdm run songs-generate

# Option 2: --project flag from the main repo
pdm run db-check --project projects/my-project
pdm run songs-generate --project projects/my-project
```

The `--project` flag can appear in any position (before or after other arguments).

### Creating a new project

```bash
# 1. Copy the template
cp -r projects/_template projects/my-new-project

# 2. Edit the config
$EDITOR projects/my-new-project/config.toml

# 3. Create the expected subdirectories
mkdir -p projects/my-new-project/{data,songs/{custom,unofficialV3,officially_released_songs,copyright_issues},setlists,images/{bg,cover,custom},logs}

# 4. Run the pipeline
pdm run clear-db --project projects/my-new-project
pdm run update-json --project projects/my-new-project
pdm run update-db --project projects/my-new-project
pdm run db-check --project projects/my-new-project
pdm run songs-generate --project projects/my-new-project
```

See [`projects/_template/README.md`](projects/_template/README.md) for the full checklist.

### Config reference (`[project]` section)

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Unique project identifier (used in cache keys) |
| `display-name` | string | Human-readable project name |
| `voice-versions` | list[str] | Ordered voice versions (e.g. `["v1", "v2", "v3"]`) |
| `duet-group-name` | string | "Singer" value for duets in `dates.csv` (e.g. `"Twins"`) |

Each `[[project.artists]]` entry:

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Canonical singer name in DB (e.g. `"Neuro"`) |
| `flag` | string | DB flag token (e.g. `"neuro"`) |
| `display-name` | string | ID3 tag name (e.g. `"Neuro-Sama"`) |
| `cover-suffix` | string | Token in cover-image filenames (e.g. `"neuro"`) |
| `album-artist` | string | TPE2/TSO2 album-artist value |

## Repo organization
### Top level
- `ai_vt_singer/`: The core, project-agnostic source code package (formerly `neuro/`).
- `metadata_utils/`: Unofficial-Archive helpers (enables writing/reading the JSON metadata payload in the ID3 comment frame).
- `projects/`: One directory per cover-artist project.
  - `projects/neuro/`: The Neuro Twins project (the one this README documents in detail).
  - `projects/_template/`: The scaffold for bootstrapping a new project (see its README).
- `pyproject.toml`: Package definition, dependencies, and the `pdm run` command entrypoints.
- `AGENTS.md`: Guide for AI coding agents working on this repo.

### Per project (e.g. `projects/neuro/`)
Every project is self-contained with its own `config.toml` and data. For the Neuro project:
- `config.toml`: The project's configuration (presets, artists, drive remotes). Details [here](#config-file).
- `data/`: Databases and reference data. The song library exists in two formats that must stay identical: `songs.csv` and `songs.db` (sqlite). `songs_new.json` is the review buffer (not the DB). Also `dates.csv`, `official_covers.csv`, `original_songs.csv`, `copyright_issues.csv`, `microphones.csv` and `dates_v12.csv`.
- `setlists/`: The setlists (source of truth for each karaoke), grouped by voice version (`v1 voice/`, `v2 voice/`, `v3 voice/`). The code also recognizes a `non-karaoke/` subfolder (e.g. `v3 voice/non-karaoke/`) for non-karaoke streams, which is currently empty.
- `songs/`: Input audio (not on GitHub, pulled from the drive): `custom/`, `unofficialV3/`, `officially_released_songs/`, `copyright_issues/`. A song's `File_IN` is stored relative to the project root.
- `images/`: Cover images, not hosted on GitHub, should be available on my drive (see [This section](#for-someone-using-this-project)). Subdirs: `bg/` (backgrounds), `cover/` (dated covers), `custom/`, `github/` (the README screenshots). The date text on thumbnails is generated by `thumbnails-generate` by drawing onto `images/cover/`.
- `fonts/`: Fonts used for the date text on thumbnails.
- `logs/`: Run logs.
- `out/`: The generated output (not on GitHub): `unofficial_releases/` and `official_releases/`, each with per-preset subdirs plus an `albums/` tree.

### Markdown
- `Song List.md`: List of all (I think?) the songs present, grouped by date mostly
- `Duplicates.md`: List of duplicates, see [what are duplicates](#what-are-duplicates)

### Code files
All of these live in the `ai_vt_singer/` package.
- `__init__.py`: `get_project()` accessor (loads + caches the active `Project`) and public re-exports
- `artists.py`: `CoverArtist` and `Project` dataclasses (multi-project data model)
- `cli.py`: `chdir_to_project()` — shared helper for the `--project <dir>` CLI flag
- `config.py`: `load_project()` — parses `config.toml` into a `Project` instance (requires a `[project]` section)
- `_shortcuts.py`: Quick CLI shortcuts (drive pull/push, etc.)
- `checks.py`: Various checks on database
- `detection.py`: Searches files matching regex patterns
- `file_tags.py`: Manages tags for files (artists, titles, etc...)
- `json_to_csv.py`: Transfers the data from new batch JSON to the database
- `polars_utils.py`: Utilitary functions related to the `polars` library (preset filtering, flag matching, caching)
- `run.py`: Mainly top-level functions that run the whole generation process
- `thumbnails.py`: Generates thumbnails with dates for songs
- `utils.py`: Utilitary common functions

## Credits
- All artists for thumbnails are (to my knowledge) cited in [the images README](./projects/neuro/images/README.md)

### From Discord
- Thanks to fujinshu for their work on identifying the key and tempo of songs
- Thanks to zhe_vlach_varon for finding the many issues in track numbering
- Thanks to ninjakai03 (mm2wood) and the people working on the other karaoke archive (from which I got the ARG songs) for their contribution (including pointing out missing songs)

## License
<sup>
Licensed under either of <a href="LICENSE-APACHE">Apache License, Version
2.0</a> or <a href="LICENSE-MIT">MIT license</a> at your option.
</sup>

<br>

<sub>
Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion by you, as defined in the Apache-2.0 license, shall be
dual licensed as above, without any additional terms or conditions.
</sub>
