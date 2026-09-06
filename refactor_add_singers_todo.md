# Refactoring Plan: Multi-Project Cover Artist Support

Goal: make it easy to add more cover artist "projects" alongside the Neuro Twins, each with
separate databases, input files, and output destinations.

---

## 1. Current State — Where the Neuro Twins Assumption Lives

~80 hardcoded references across 8 files, in 4 categories.

### A. Singer Identity (who sings) — ~30 sites

| File | Lines | What's hardcoded |
|------|-------|------------------|
| `neuro/utils.py` | 523–555 | `get_flags()`: `lead_singer == 'Neuro'`, `== 'Evil'`, `cover_artist == 'Neuro & Evil'`, collab patterns. `post_process_flags()`: strips `'evil;'`/`'neuro;'` for twin duets |
| `neuro/file_tags.py` | 56–65 | `Flags` dataclass: fixed `neuro: bool`, `evil: bool` fields |
| `neuro/file_tags.py` | 325–329 | `who` property: `if self.flags.evil: return "evil"` / `if self.flags.neuro: return "neuro"` |
| `neuro/file_tags.py` | 376–381 | `album_artist`: returns `"Neuro-Sama/Evil Neuro"`, `"Neuro [v1]"`, `"Neuro [v2]"` |
| `neuro/file_tags.py` | 394–409 | `name_tag`: returns `"Neuro"`, `"Evil"`, `"Duet"`, `"Neuro + Vedal"`, `"Neuro v1"`, `"Neuro v2"` |
| `neuro/file_tags.py` | 314, 593 | `get_vorbis_frames()`: `"PERFORMER": "Neuro-Sama/Evil Neuro"`; `CustomSong.apply_id3()`: same |
| `neuro/file_tags.py` | 522 | `CustomSong._who_fallback`: returns `"twins"` |
| `neuro/detection.py` | 330, 356 | `parse_setlist()`: default `lead_singer = "Neuro"`; singer-change: `fields[0].startswith("Neuro") or fields[0] == "Evil"` |
| `neuro/detection.py` | 155–159 | `extract_unofficialV3()`: `cover_artist.startswith('Neuro')` |
| `neuro/detection.py` | 267–274 | `extract_official()`: infers lead singer from `'Neuro' in Cover Artist` / `'Evil' in Cover Artist` |
| `neuro/detection.py` | 449–451, 634 | `is_twin_duet_stream()`: checks `Cover Artist == 'Neuro & Evil'`; renames album via `.replace('Neuro', 'Twins').replace('Evil', 'Twins')` |
| `neuro/json_to_csv.py` | 67, 71 | `update_db()`: `if singer == 'Neuro & Evil': singer = "Twins"`; date filter: `song['Cover Artist'] in ['Neuro', 'Evil', 'Neuro & Evil']` |
| `neuro/json_to_csv.py` | 273–276 | `get_most_recent_version()`: `if lead_singer == 'Neuro': flags = flags.replace('evil', 'neuro')` (and vice versa) |
| `neuro/thumbnails.py` | 142, 149, 165–176, 222 | `check_stream()`: `Singer not in ["Neuro", "Evil", "Twins"]`; `singer_match()`: `case "Neuro"`, `case "Evil"`, `case "Twins"`; loop: `for who in ['Neuro', 'Evil']` |
| `config.toml` | 35, 97, 139–332 | 30 preset definitions referencing `neuro`, `evil`, `duet` flags |

### B. Project Paths (where things are) — ~20 sites

| File | What's hardcoded |
|------|------------------|
| `neuro/__init__.py` (all 48 lines) | `SONGS_JSON`, `SONGS_CSV`, `SONGS_DB`, `DATES_CSV`, `IMAGES_*`, `SONG_ROOT_DIR`, `DRIVE_DIR`, `CUSTOM_DIR`, `UNOFFICIALV3_DIR`, `OFFICIAL_RELEASE_DIR`, `COPYRIGHT_ISSUES_DIR`, `SETLISTS_DIR`, `OUT_ROOT_DIR`, `OUT_UNOFFICIAL_DIR`, `OUT_OFFICIAL_DIR`, `FONTS_DIR` — all module-level constants |
| `neuro/_shortcuts.py` (13–23, 73–77) | Drive names: `Neuro-Sings-ZVV`, `Neuro-Sings-ZVV-official-releases`, `unofficialV3`; `PUBLIC_DEST`, `PRIVATE_DEST` |

### C. Flag Vocabulary — ~10 sites

The flags `neuro`, `evil`, `duet`, `collab`, `v1`, `v2`, `v3` are treated as a closed set.
The `Flags` dataclass in `file_tags.py` has exactly these fields, and the flag logic in
`utils.py` only knows about `neuro` and `evil` as singer identifiers.

### D. Domain Logic — ~10 sites

| File | What's hardcoded |
|------|------------------|
| `neuro/detection.py` | `is_twin_duet_stream()` concept (all songs in album are `'Neuro & Evil'`); ARG handling (`'Study-sama'`) |
| `neuro/utils.py` | `get_flags()`: `'[v1]' in cover_artist`, `'[v2]' in cover_artist` voice version detection; `lead_singer == 'Study-sama'` ARG special case |
| `neuro/thumbnails.py` | `singer_match()` maps Neuro/Evil/Twins to specific background image indices; `DuetVersion` type alias `Literal["v1", "v2v1", "v2"]` |

---

## 2. Target Architecture

Introduce a **Project** abstraction that encapsulates everything about one "cover artist group",
and a **CoverArtist** type for each individual singer. Code references these via the project
context instead of hardcoded strings.

### 2.1 New data model

```python
# neuro/artists.py (new file)

@dataclass(frozen=True)
class CoverArtist:
    """One cover singer within a project."""
    name: str          # "Neuro", "Evil", "Vedal"
    flag: str          # "neuro", "evil", "vedal"  (DB flag token)
    display_name: str  # "Neuro-Sama", "Evil Neuro"  (for ID3 tags)
    cover_suffix: str  # "neuro", "evil"  (for image filenames)
    album_artist: str  # "Neuro-Sama/Evil Neuro"  (TPE2/TSO2 value)


@dataclass
class Project:
    """A complete project: one or more cover artists sharing a DB, input, and output."""
    name: str                          # "neuro", "vedal"
    display_name: str                  # "Neuro Twins"
    artists: tuple[CoverArtist, ...]   # the singers
    voice_versions: tuple[str, ...]    # ("v1", "v2", "v3")
    duet_group_name: str               # "Twins" (used for album rename + dates table)

    # --- paths (all resolved relative to CWD at load time) ---
    data_dir: Path                     # data/
    songs_csv: Path                    # data/songs.csv
    songs_db: Path                     # data/songs.db
    songs_json: Path                   # data/songs_new.json
    dates_csv: Path                    # data/dates.csv
    song_root: Path                    # songs/
    setlists_dir: Path                 # setlists/
    images_covers_dir: Path            # images/cover/
    images_custom_dir: Path            # images/custom/
    images_bg_dir: Path                # images/bg/
    out_root: Path                     # out/
    out_unofficial: Path               # out/unofficial_releases/
    out_official: Path                 # out/official_releases/
    fonts_dir: Path                    # fonts/

    # --- drive ---
    drive_public: str | None           # rclone remote name
    drive_private: str | None          # rclone remote name
    drive_source: str | None           # rclone remote name for source audio

    # --- helpers ---
    def singer_names(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.artists)

    def duet_cover_artist(self) -> str:
        """The 'Cover Artist' string for a duet between all artists (e.g. 'Neuro & Evil')."""
        return ' & '.join(a.name for a in self.artists)

    def flag_for(self, singer_name: str) -> str:
        for a in self.artists:
            if a.name == singer_name:
                return a.flag
        raise KeyError(singer_name)

    def singer_for_flag(self, flag: str) -> CoverArtist:
        for a in self.artists:
            if a.flag == flag:
                return a
        raise KeyError(flag)

    def all_singer_flags(self) -> tuple[str, ...]:
        return tuple(a.flag + ';' for a in self.artists)
```

### 2.2 Config format (extended `config.toml`)

```toml
# ── project identity ──────────────────────────────────────────────
[project]
name = "neuro"
display-name = "Neuro Twins"
voice-versions = ["v1", "v2", "v3"]
duet-group-name = "Twins"

[[project.artists]]
name = "Neuro"
flag = "neuro"
display-name = "Neuro-Sama"
cover-suffix = "neuro"
album-artist = "Neuro-Sama/Evil Neuro"

[[project.artists]]
name = "Evil"
flag = "evil"
display-name = "Evil Neuro"
cover-suffix = "evil"
album-artist = "Neuro-Sama/Evil Neuro"

# ── drive ─────────────────────────────────────────────────────────
[drive]
public = "Neuro-Sings-ZVV"
private = "Neuro-Sings-ZVV-official-releases"
source = "unofficialV3"

# ── output (unchanged) ────────────────────────────────────────────
[output]
use-root = true
out-root = "out"
make-links = true

# ── features (unchanged) ──────────────────────────────────────────
[features]
activated = ["mp3gain"]
# ...

# ── presets (unchanged) ───────────────────────────────────────────
[[Presets]]
# ...
```

For a **second project** (e.g. Vedal), create a sibling directory `vedal/` with its own
`config.toml`, `data/`, `songs/`, `setlists/`, `images/`, and `out/`. The code is the same
package; only the config and data differ. The user `cd`s into the project directory and runs
commands — no CLI flag needed since `ROOT_DIR = Path(".")` already makes everything CWD-relative.

### 2.3 Module restructure

```
neuro/
  __init__.py          # thin re-exports, get_project() accessor
  artists.py           # NEW: CoverArtist, Project dataclasses
  config.py            # NEW: load_project(config_path) → Project
  polars_utils.py      # load_db/load_dates take Project param
  utils.py             # get_flags/post_process_flags take Project param
  file_tags.py         # Song/DriveSong/CustomSong take Project in __init__
  detection.py         # all extract_* take Project
  json_to_csv.py       # update_db/clear_db take Project
  checks.py            # all check_* take Project
  run.py               # generate_* take Project
  thumbnails.py        # generate_* take Project
  _shortcuts.py        # drive ops take Project
```

---

## 3. Phased Implementation

Each phase is independently shippable and backward-compatible.

### Phase 1 — Extract the `Project` and `CoverArtist` dataclasses (1–2 days)

**Goal:** Define the types, load them from config, and make them available everywhere. No behavior changes.

- [x] **Create `neuro/artists.py`** with `CoverArtist` and `Project` dataclasses (sketch above).

- [x] **Create `neuro/config.py`** with:
  ```python
  def load_project(config_path: Path = Path("config.toml")) -> Project:
      """Parse config.toml and return a Project instance."""
      with open(config_path, "rb") as f:
          raw = tomllib.load(f)
      # ... build CoverArtist list, resolve paths, return Project
  ```
  If `[project]` section is absent, synthesize a `Project` from the existing module-level
  constants with `artists = (Neuro, Evil)` for backward compat.

- [x] **Add a `get_project()` accessor** in `neuro/__init__.py`:
  ```python
  from neuro.config import load_project
  _project: Project | None = None

  def get_project() -> Project:
      global _project
      if _project is None:
          _project = load_project()
      return _project
  ```

- [x] **Add the `[project]` section to `config.toml`** with the current Neuro Twins values,
      so the new config path is exercised.

**Files touched:** `neuro/artists.py` (new), `neuro/config.py` (new), `neuro/__init__.py`, `config.toml`.

**Verification:** Run `db-check` — should pass unchanged.

---

### Phase 2 — Parameterize paths (2–3 days)

**Goal:** Replace all module-level path constants with `Project` attributes. Mechanical but wide-reaching.

- [x] **`neuro/__init__.py`:** Keep existing constants for backward compat (marked deprecated).
      Add `get_project()` accessor.

- [x] **`neuro/polars_utils.py`:**
  - `load_db(as_db=True, root=ROOT_DIR)` → `load_db(as_db=True, project: Project | None = None)`
  - `load_dates(as_db=True, root=ROOT_DIR)` → `load_dates(as_db=True, project: Project | None = None)`
  - Cache key includes `project.name` to avoid cross-project cache pollution.

- [x] **`neuro/detection.py`:**
  - `get_files(songs)` → use `project.song_root` subdirs instead of `DRIVE_DIR`, `CUSTOM_DIR`, etc.
  - `extract_all()` → thread `project` to all `extract_*` calls.
  - `export_json(out)` → use `project.songs_json` instead of `SONGS_JSON`.

- [x] **`neuro/json_to_csv.py`:**
  - `clear_db()` → use `project.songs_csv`, `project.songs_db`, `project.dates_csv`.
  - `update_db()` → same, plus `project.songs_json`.

- [x] **`neuro/checks.py`:**
  - All `check_*` functions → use `get_project()` for paths.
  - `check_are_dbs_identical()` → compare the project's CSV vs SQLite.

- [x] **`neuro/run.py`:**
  - `load_config()` → return `(config_dict, project)` instead of `(config_dict, OUT_ROOT)`.
  - `generate_from_preset()` → use `project.out_unofficial` / `project.out_official` instead of
    the hardcoded `"unofficial_releases"` / `"official_releases"` strings in `resolve_output_paths()`.

- [x] **`neuro/_shortcuts.py`:**
  - Drive names → `project.drive_public`, `project.drive_private`, `project.drive_source`.
  - All rclone path constructions → use `project` paths.

- [x] **`neuro/thumbnails.py`:**
  - `IMAGES_BG_DIR`, `IMAGES_COVERS_DIR`, `IMAGES_CUSTOM_DIR` → `project.images_bg_dir`, etc.
  - `FONT_PATH` → `project.fonts_dir / "First Coffee.ttf"`.

**Files touched:** `neuro/__init__.py`, `neuro/polars_utils.py`, `neuro/detection.py`,
`neuro/json_to_csv.py`, `neuro/checks.py`, `neuro/run.py`, `neuro/_shortcuts.py`, `neuro/thumbnails.py`.

**Verification:** Run the full test procedure (`clear-db` → `update-json` → `update-db` →
`db-check` → `songs-generate`) — output must be identical to before.

---

### Phase 3 — Generalize singer identity (3–5 days)

**Goal:** Replace all hardcoded `"Neuro"`/`"Evil"`/`"Neuro & Evil"` string checks with lookups
through `project.artists`. This is the core of the refactoring.

- [ ] **3a. `neuro/utils.py` — `get_flags()`:**

  ```python
  # BEFORE
  if lead_singer == 'Neuro':
      flags += 'neuro;'
  if lead_singer == 'Evil':
      flags += 'evil;'
  if cover_artist == 'Neuro & Evil':
      flags += 'duet;'
  elif ('Neuro ' in cover_artist and ' & ' in cover_artist and 'Evil' not in cover_artist) or 'Evil & ' in cover_artist or 'Neuro, Evil, ' in cover_artist:
      flags += 'collab;'

  # AFTER
  def get_flags(song: SongEntry, project: Project) -> str:
      ...
      if lead_singer in project.singer_names():
          flags += project.flag_for(lead_singer) + ';'
      if cover_artist == project.duet_cover_artist():
          flags += 'duet;'
      # collab: cover_artist contains a project singer + ' & ' + a non-project name
      has_project_singer = any(s in cover_artist for s in project.singer_names())
      has_other = ' & ' in cover_artist and cover_artist != project.duet_cover_artist()
      if has_project_singer and has_other:
          flags += 'collab;'
      ...
  ```

- [ ] **3b. `neuro/utils.py` — `post_process_flags()`:**

  ```python
  # BEFORE
  if is_twin_duet:
      flags = flags.replace('evil;', '').replace('neuro;', '')
  if cover_artist == 'Neuro & Evil' and 'original' in flags:
      flags = flags.replace('neuro;', '').replace('evil;', '')

  # AFTER
  def post_process_flags(flags, cover_artist, project: Project, is_twin_duet=False):
      singer_flags = project.all_singer_flags()  # ('neuro;', 'evil;')
      if is_twin_duet:
          for sf in singer_flags:
              flags = flags.replace(sf, '')
      if cover_artist == project.duet_cover_artist() and 'original' in flags:
          for sf in singer_flags:
              flags = flags.replace(sf, '')
          if 'duet;' not in flags:
              flags += 'duet;'
      return flags
  ```

- [ ] **3c. `neuro/file_tags.py` — `Flags` dataclass:**

  Keep `neuro: bool` and `evil: bool` for backward compat. Add a generic field:

  ```python
  @dataclass
  class Flags:
      # ... existing fields unchanged ...
      neuro: bool
      evil: bool
      # new: generic singer flag map, populated from project
      singer_flags: dict[str, bool] = field(default_factory=dict)
  ```

  `init_flags()` populates `singer_flags` from `project.artists` in addition to the
  existing fields.

- [ ] **3d. `neuro/file_tags.py` — `who` property:**

  ```python
  # BEFORE
  @property
  def who(self) -> str:
      if self.flags.evil:
          return "evil"
      if self.flags.neuro:
          return "neuro"
      return self._who_fallback

  # AFTER
  @property
  def who(self) -> str:
      for artist in self._project.artists:
          if self.flags.singer_flags.get(artist.flag, False):
              return artist.cover_suffix
      return self._who_fallback
  ```

- [ ] **3e. `neuro/file_tags.py` — `name_tag`:**

  ```python
  # BEFORE
  @property
  def name_tag(self) -> str:
      if self.flags.v1: return "Neuro v1"
      if self.flags.v2: return "Neuro v2"
      if self.title == "Chinatown Blues": return "Neuro + Vedal"
      if self.flags.duet: return "Duet"
      if self.flags.evil: return "Evil"
      if self.flags.neuro: return "Neuro"
      raise ValueError(...)

  # AFTER
  @property
  def name_tag(self) -> str:
      for v in self._project.voice_versions:
          if getattr(self.flags, v, False):
              return f"{self._project.artists[0].name} {v}"
      if self.flags.duet:
          return "Duet"
      for artist in self._project.artists:
          if self.flags.singer_flags.get(artist.flag, False):
              return artist.name
      raise ValueError(f"Song '{self.file}' has no singer flags!")
  ```

- [ ] **3f. `neuro/file_tags.py` — `album_artist`:**

  ```python
  # BEFORE
  @property
  def album_artist(self) -> str:
      if self.flags.v1 and self.date < "2023-05-27":
          return "Neuro [v1]"
      if self.flags.v2 and self.date <= "2023-06-08" and self.cover_artist == "Neuro [v2]":
          return "Neuro [v2]"
      return "Neuro-Sama/Evil Neuro"

  # AFTER
  @property
  def album_artist(self) -> str:
      for artist in self._project.artists:
          if artist.name in self.cover_artist:
              return artist.album_artist
      return self._project.artists[0].album_artist
  ```

- [ ] **3g. `neuro/file_tags.py` — `get_vorbis_frames()` and `CustomSong.apply_id3()`:**

  Replace `"Neuro-Sama/Evil Neuro"` with `self._project.artists[0].album_artist`.

- [ ] **3h. `neuro/detection.py` — `parse_setlist()`:**

  ```python
  # BEFORE (line 330)
  lead_singer = "Neuro"
  # AFTER
  lead_singer = project.artists[0].name

  # BEFORE (line 356)
  if not is_album_info_line and (fields[0].startswith("Neuro") or fields[0] == "Evil"):
  # AFTER
  singer_names = project.singer_names()
  if not is_album_info_line and any(fields[0].startswith(s) for s in singer_names):
  ```

- [ ] **3i. `neuro/detection.py` — `is_twin_duet_stream()`:**

  ```python
  # BEFORE
  def is_twin_duet_stream(album_name: str, songs: list) -> bool:
      if album_name in neutils.get_non_karaoke_album_names():
          return False
      return all(song['Cover Artist'] == 'Neuro & Evil' for song in songs)

  # AFTER
  def is_twin_duet_stream(album_name: str, songs: list, project: Project) -> bool:
      if album_name in neutils.get_non_karaoke_album_names():
          return False
      duet_name = project.duet_cover_artist()
      return all(song['Cover Artist'] == duet_name for song in songs)
  ```

  Album rename (line 450):
  ```python
  # BEFORE
  twin_album_stream_title = album.replace('Neuro', 'Twins').replace('Evil', 'Twins')
  # AFTER
  twin_album_stream_title = album
  for a in project.artists:
      twin_album_stream_title = twin_album_stream_title.replace(a.name, project.duet_group_name)
  ```

- [ ] **3j. `neuro/detection.py` — `extract_official()`:**

  ```python
  # BEFORE
  if 'Neuro' in song['Cover Artist'] and 'Evil' in song['Cover Artist']:
      lead_singer = 'Neuro'
  elif 'Neuro' in song['Cover Artist']:
      lead_singer = 'Neuro'
  elif 'Evil' in song['Cover Artist']:
      lead_singer = 'Evil'

  # AFTER
  def _infer_lead_singer(cover_artist: str, project: Project) -> str:
      for a in project.artists:
          if a.name in cover_artist:
              return a.name
      raise ValueError(f"Cannot infer lead singer from '{cover_artist}'")
  ```

- [ ] **3k. `neuro/json_to_csv.py` — `update_db()`:**

  ```python
  # BEFORE (line 67)
  if singer == 'Neuro & Evil':
      singer = "Twins"
  # AFTER
  if singer == project.duet_cover_artist():
      singer = project.duet_group_name

  # BEFORE (line 71)
  if ... song['Cover Artist'] in ['Neuro', 'Evil', 'Neuro & Evil']:
  # AFTER
  valid_cover_artists = set(project.singer_names()) | {project.duet_cover_artist()}
  if ... song['Cover Artist'] in valid_cover_artists:
  ```

- [ ] **3l. `neuro/json_to_csv.py` — `get_most_recent_version()`:**

  ```python
  # BEFORE (lines 273-276)
  if lead_singer == 'Neuro':
      flags = flags.replace('evil', 'neuro')
  if lead_singer == 'Evil':
      flags = flags.replace('neuro', 'evil')

  # AFTER
  lead_flag = project.flag_for(lead_singer)
  for a in project.artists:
      if a.flag != lead_flag and a.flag + ';' in flags:
          flags = flags.replace(a.flag + ';', lead_flag + ';')
  ```

- [ ] **3m. `neuro/thumbnails.py` — `check_stream()`, `singer_match()`, `generate_main()`:**

  ```python
  # BEFORE
  def check_stream(stream):
      if stream["Singer"] not in ["Neuro", "Evil", "Twins"]:
          raise ValueError(...)
  # AFTER
  def check_stream(stream, project: Project):
      valid = set(project.singer_names()) | {project.duet_group_name}
      if stream["Singer"] not in valid:
          raise ValueError(f"Wrong singer {stream['Singer']}")
  ```

  The `singer_match()` function and `SOLO_BG`/`DUET_BG` image lists are the most
  Neuro-specific part. Add to `Project`:
  ```python
  bg_solo_images: dict[str, list[str]]   # singer_name → [bg_filename_per_voice_version]
  bg_duet_images: list[str]              # [bg_filename_per_duet_version]
  ```
  `singer_match()` becomes a lookup into these project-configured lists.

- [ ] **3n. `Song.__init__` — store the project reference:**

  Add `self._project: Project = project` to `Song.__init__`, passed from `classify_song()`
  in `run.py` (which already has the project in scope).

**Files touched:** `neuro/utils.py`, `neuro/file_tags.py`, `neuro/detection.py`,
`neuro/json_to_csv.py`, `neuro/thumbnails.py`, `neuro/run.py`.

**Verification:** Run `db-check` and `songs-generate` — output must be byte-identical to
pre-refactor.

---

### Phase 4 — CLI: project selection (1 day)

**Goal:** Let the user pick which project to operate on.

**Recommended approach (zero CLI changes):** Each project lives in its own directory.
The user `cd`s into it and runs the commands. The existing `ROOT_DIR = Path(".")` already
makes everything CWD-relative.

**Alternative (if a single checkout must serve multiple projects):** Add a `--project <dir>`
argument to the entry points in `pyproject.toml`. The default is `.` (current directory).

- [ ] Decide: separate directories (recommended) vs `--project` flag.
- [ ] If `--project` flag: add to all entry points, resolve `config_path` from the arg.
- [ ] If separate directories: no code change needed, just document the workflow.

**Files touched:** possibly `pyproject.toml`, `neuro/config.py`.

---

### Phase 5 — Cleanup and documentation (1–2 days)

- [ ] Remove deprecated module-level constants from `neuro/__init__.py`
      (or keep as thin wrappers around `get_project()` for one more release).
- [ ] Update `AGENTS.md` to document the multi-project model:
  - How to create a new project directory
  - The `[project]` config section reference
  - The `CoverArtist` and `Project` data model
  - The per-project test procedure
- [ ] Add a `projects/_template/` directory with a minimal `config.toml` and directory
      structure that users can copy to bootstrap a new project.
- [ ] Update `README.md` with a "Multi-project" section.

---

## 4. Migration / Backward Compatibility

| Phase | Backward compat? | How |
|-------|-----------------|-----|
| 1 | Yes | `[project]` section is optional; if absent, code synthesizes a Project from the old constants |
| 2 | Yes | `load_db(project=None)` defaults to the global project; old call sites still work |
| 3 | Yes | `Flags.neuro`/`Flags.evil` remain as fields; old preset flags in `config.toml` still work (flag tokens unchanged) |
| 4 | Yes | Separate directories require no code change; `--project` flag is optional |
| 5 | Break | Remove deprecated constants — do in a major version bump |

The existing Neuro Twins project continues to work unchanged through all phases. A new
project is created by copying the directory structure and editing `config.toml` — no code
changes needed.

---

## 5. Effort Estimate

| Phase | Scope | Est. effort | Risk |
|-------|-------|------------|------|
| 1 — Data model | 2 new files, config change | 1–2 days | Low |
| 2 — Paths | 8 files, mechanical replacement | 2–3 days | Low |
| 3 — Singer identity | 6 files, logic changes | 3–5 days | **Medium** (flag logic is subtle) |
| 4 — CLI | 1–2 files | 1 day | Low |
| 5 — Cleanup | Docs, templates | 1–2 days | Low |
| **Total** | | **~1.5–2 weeks** | |

---

## 6. Key Risk & Mitigation

The highest-risk area is **Phase 3 (singer identity)** because the flag logic in
`get_flags()`, `post_process_flags()`, and `get_most_recent_version()` has subtle
interactions (e.g. the `lead_singer == 'Neuro': flags.replace('evil', 'neuro')` logic).

Mitigation:

1. Write the generalized functions first, then write a **differential test** that runs both
   the old and new implementations over the full existing DB and asserts identical flag
   output for every song.
2. The `check_group_coverage()` function already validates that presets partition the DB —
   run it after each sub-step.
3. The full rebuild test procedure (`clear-db` → `update-json` → `update-db` → `db-check`)
   is the end-to-end gate.
