# Project Template

This directory contains the minimal scaffolding to bootstrap a new cover-artist project.
The **Neuro Twins project** at `projects/neuro/` is a complete, working reference — diff
against its `config.toml` and directory layout if you're unsure about any field.

> Note: the `ai_vt_singer/` package is project-agnostic and lives at the repo root. A project
> is selected simply by `cd`-ing into its directory (or passing `--project <name>`) — the active
> project's `config.toml` is read from the current working directory.

## How to create a new project

1. **Copy this template** to a new directory:
   ```bash
   cp -r projects/_template projects/my-new-project
   ```

2. **Edit `config.toml`** in the new directory:
   - Set `[project]` identity (name, display-name, voice-versions, duet-group-name)
   - Define your `[[project.artists]]` (at least one singer)
   - Configure `[drive]` remotes if using Google Drive sync
   - Define your `[[Presets]]`

3. **Create the expected directory structure**:
   ```
   projects/my-new-project/
   ├── config.toml          # ← you edited this
   ├── data/                # songs.csv, songs.db, songs_new.json, dates.csv (created by clear-db)
   ├── songs/               # input audio
   │   ├── custom/
   │   ├── unofficialV3/
   │   ├── officially_released_songs/
   │   └── copyright_issues/
   ├── setlists/            # karaoke setlist files (txt)
   ├── images/
   │   ├── bg/
   │   ├── cover/
   │   └── custom/
   ├── fonts/               # (optional, only if generating thumbnails)
   ├── logs/                # (created automatically)
   └── out/                 # (created automatically by songs-generate)
   ```

4. **Run the pipeline** from the project root (or use `--project`):
   ```bash
   # Option A: cd into the project
   cd projects/my-new-project
   pdm run clear-db
   pdm run update-json
   pdm run update-db
   pdm run db-check
   pdm run songs-generate

   # Option B: use --project from the main repo (projects/ prefix is optional)
   pdm run clear-db --project my-new-project
   pdm run update-json --project my-new-project
   pdm run update-db --project my-new-project
   pdm run db-check --project my-new-project
   pdm run songs-generate --project my-new-project
   ```

## Requirements for a working project

- At least one `[[project.artists]]` entry
- A valid `[[Presets]]` definition (at least one preset that matches your flags)
- Input audio files in `songs/` (if running `update-json`)
- Setlist files in `setlists/` (if running `update-json`)
- Cover images in `images/cover/` and `images/bg/` (if running `thumbnails-generate`)

Optional data files (only needed if you have official releases / original songs to import):

- `data/official_covers.csv` — pipe-separated, columns `Date|Title|Artist|Cover Artist`.
  If absent, `update-json` skips official-cover detection.
- `data/original_songs.csv` — comma-separated, columns `Date,Title,Artist`.
  If absent, `update-json` skips original-song detection.

## Notes

- The `name` in `[project]` should be a valid Python identifier (used in cache keys).
- The `flag` for each artist must match the flag tokens you use in your `Flags` DB column.
- `duet-group-name` is used for the "Singer" column in `dates.csv` when a song is a duet
  (e.g. `"Twins"` for Neuro & Evil).
- Each project is fully self-contained: its own DB, its own output, its own Drive remotes.
