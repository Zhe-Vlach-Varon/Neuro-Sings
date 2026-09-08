# Phase 7 — Rename, Relocate, and Clean Up

Goal: complete the multi-project architecture by (1) renaming the core package to a
generic name, (2) making the Neuro Twins project a first-class project under
`projects/`, and (3) removing remaining hardcoded assumptions that assume the Neuro
project layout.

---

## Target Layout

```
Neuro-Sings/              (repo root — generic, no project identity)
  ai_vt_singer/           (core logic package, renamed from neuro/)
    __init__.py
    artists.py
    config.py
    cli.py
    polars_utils.py
    utils.py
    file_tags.py
    detection.py
    json_to_csv.py
    checks.py
    run.py
    thumbnails.py
    _shortcuts.py
  metadata_utils/         (unchanged, sibling package)
  projects/
    _template/            (existing template)
    neuro/                (Neuro Twins — moved here from repo root)
      config.toml
      data/
      fonts/
      images/
      setlists/
      songs/              (gitignored)
      out/                (gitignored)
      logs/               (gitignored)
  pyproject.toml          (entry points updated)
  .gitignore              (updated)
  AGENTS.md               (updated)
  README.md               (updated)
```

---

## Step 1 — Rename `neuro/` → `ai_vt_singer/`

### 1a. Rename the directory

```bash
git mv neuro ai_vt_singer
```

### 1b. Update internal imports

All modules currently import via `from neuro import ...` or `import neuro.utils as neutils`.
Switch to **relative imports** within the package (cleaner, and decouples the package name
further).

| Current | Replacement |
|---|---|
| `from neuro import LOG_DIR, get_project, ...` | `from . import LOG_DIR, get_project, ...` |
| `from neuro.artists import Project` | `from .artists import Project` |
| `from neuro.cli import chdir_to_project` | `from .cli import chdir_to_project` |
| `from neuro.polars_utils import load_db, ...` | `from .polars_utils import load_db, ...` |
| `from neuro.utils import format_logger, ...` | `from .utils import format_logger, ...` |
| `import neuro.utils as neutils` | `from . import utils` |
| `from neuro import get_project` | `from . import get_project` |

Additionally, all `neutils.<func>` call sites (in `detection.py` and `json_to_csv.py`)
become `utils.<func>`.

Files affected (every `.py` in `ai_vt_singer/`):
- `__init__.py` (its own re-exports: `from .artists import ...`, `from .config import ...`)
- `config.py` (the deferred `import neuro` in `_synthesized_project()` → `import ai_vt_singer`
  or `from .. import ...` — actually this needs care, see below)
- `artists.py` (no self-imports, docstrings only)
- `cli.py` (docstring references)
- `polars_utils.py`
- `utils.py`
- `file_tags.py`
- `detection.py`
- `json_to_csv.py`
- `checks.py`
- `run.py`
- `thumbnails.py`
- `_shortcuts.py`

**Special case: `config.py::_synthesized_project()`** currently does `import neuro` (deferred
to avoid circular import). After the rename this becomes `import ai_vt_singer` — but since we
're inside the package, a relative `from .. import ...` won't work (there's no parent package
in the normal sense). The simplest fix: change it to
```python
from . import DATA_DIR, SONGS_CSV, ...  # relative import from __init__.py
```
which works because by the time `_synthesized_project()` is called (at runtime, not import time),
the package is fully loaded.

### 1c. Update `pyproject.toml` entry points

Every entry point changes from `neuro.<module>:<func>` to `ai_vt_singer.<module>:<func>`:

```toml
[project.scripts]
songs-generate = "ai_vt_singer.run:generate_songs"
songs-generate-group = "ai_vt_singer.run:generate_songs_group"
albums-generate = "ai_vt_singer.run:generate_albums"
update-json = "ai_vt_singer.run:new_batch_detection"
thumbnails-generate = "ai_vt_singer.thumbnails:generate_main"
thumbnails-old = "ai_vt_singer.thumbnails:generate_oldge"
update-db = "ai_vt_singer.json_to_csv:update_db"
clear-db = "ai_vt_singer.json_to_csv:clear_db"
db-check = "ai_vt_singer.checks:all_tests"
check-group = "ai_vt_singer.run:check_group"
inputs-pull = "ai_vt_singer._shortcuts:inputs_pull"
setlists-pull = "ai_vt_singer._shortcuts:setlists_pull"
setlists-push = "ai_vt_singer._shortcuts:setlists_push"
drive-pull = "ai_vt_singer._shortcuts:drive_pull"
drive-push = "ai_vt_singer._shortcuts:drive_push"
db-sync = "ai_vt_singer._shortcuts:dbs_sync"
mp3gain_standalone = "ai_vt_singer.run:mp3gain_standalone"
setlist-check = "ai_vt_singer.detection:run_setlist_check"
```

Then run `pdm install` to regenerate the script shims.

### 1d. Update `metadata_utils` imports

`file_tags.py` line 22: `from metadata_utils import engraver as engraver` — this is an absolute
import of a sibling top-level package. It should still work after the rename since
`metadata_utils/` stays at the repo root and the PDM venv puts the repo root on `sys.path`.
No change needed here, but verify.

### 1e. Update `neuro/.gitignore`

The file `neuro/.gitignore` (if any project-specific ignore rules live there) should move to
`ai_vt_singer/.gitignore` or be merged into the root `.gitignore`.

### 1f. Verify

```bash
pdm install
pdm run db-check --project projects/neuro   # (after Step 2)
pdm run ruff check ai_vt_singer/
```

---

## Step 2 — Make the Neuro Twins project a first-class project

### 2a. Create the project directory and move files

```bash
mkdir -p projects/neuro
git mv config.toml projects/neuro/config.toml
git mv data projects/neuro/data
git mv fonts projects/neuro/fonts
git mv images projects/neuro/images
git mv setlists projects/neuro/setlists
# songs/ is gitignored — move on disk only:
mv songs projects/neuro/songs
# out/ is gitignored — move on disk only:
mv out projects/neuro/out
# logs/ is gitignored — move on disk only:
mv logs projects/neuro/logs
```

### 2b. Update `.gitignore`

Remove the root-level project entries and replace with project-scoped patterns:

```gitignore
# Project-specific (all projects)
projects/*/songs/
projects/*/out/
projects/*/logs/
projects/*/images/bg/
projects/*/images/custom/
projects/*/images/cover/
projects/*/fonts/First Coffee.otf
projects/*/fonts/First Coffee.ttf

# Remove these (no longer at root):
# songs
# logs
# images/bg
# images/custom
# images/cover
# out
# fonts/First Coffee.otf
# fonts/First Coffee.ttf
# Neuro-Sings-ZVV-official-releases
```

### 2c. Verify `--project` works from repo root

```bash
pdm run db-check --project projects/neuro
pdm run update-json --project projects/neuro
pdm run update-db --project projects/neuro
pdm run db-check --project projects/neuro
pdm run songs-generate --project projects/neuro
```

Also verify `cd projects/neuro && pdm run db-check` still works (PDM walks up to find the
`pyproject.toml` at the repo root).

### 2d. Remove the root `config.toml`

After confirming everything works, the root `config.toml` is gone (moved in 2a). If any code
still opens `"config.toml"` relative to CWD, it will now find the one in `projects/neuro/`
after chdir — which is the intended behaviour.

---

## Step 3 — Remove remaining hardcoded assumptions

These are the things that still assume the Neuro Twins project specifically:

### 3a. Hardcoded `songs/` subdirectory names

The following directory names under `songs/` are hardcoded in multiple files:
- `"drive"` — `detection.py:50`, `run.py:79`
- `"custom"` — `detection.py:49`, `run.py:77`
- `"unofficialV3"` — `detection.py:50`, `run.py:77`
- `"officially_released_songs"` — `detection.py:52`, `run.py:81`
- `"copyright_issues"` — `detection.py:53`, `run.py:81`

**Fix:** Add a `song_dirs` mapping to `Project`:
```python
# In artists.py Project dataclass:
song_dirs: dict[str, str] = field(default_factory=lambda: {
    "drive": "drive",
    "custom": "custom",
    "unofficialv3": "unofficialV3",
    "official": "officially_released_songs",
    "copyright": "copyright_issues",
})
```
Populate from config (optional `[project.song-dirs]` section), defaulting to the above.
Replace all hardcoded strings with `project.song_dirs["unofficialv3"]`, etc.

**Config (optional, in `projects/neuro/config.toml`):**
```toml
[project.song-dirs]
unofficialv3 = "unofficialV3"
official = "officially_released_songs"
# others default to the key name
```

### 3b. `UNOFFV3_EXTRA` and `UNOFFV3_DISC66`

These are Neuro-specific subdirectory names under `unofficialV3/`:
- `UNOFFV3_EXTRA = "Extra Content"` — `__init__.py:35`
- `UNOFFV3_DISC66 = "DISC 66 - ARG"` — `__init__.py:36`

Used in `detection.py` (ARG extraction) and `run.py` (classify_song).

**Fix:** Move to `Project`:
```python
arg_subdir: str | None = None  # e.g. "Extra Content/DISC 66 - ARG"
```
If `None`, the project has no ARG subdirectory (ARG extraction is a no-op).
Remove the module-level constants; use `project.arg_subdir` instead.

In `projects/neuro/config.toml`:
```toml
[project]
arg-subdir = "Extra Content/DISC 66 - ARG"
```

### 3c. `Flags` dataclass still has `neuro` and `evil` as named fields — ✅ DONE

In `file_tags.py`, the `Flags` dataclass has:
```python
neuro: bool
evil: bool
```

These are used by `init_flags()` and the `who` property. The `singer_flags: dict` field was
added in Phase 3 but the named fields were kept for backward compat.

**Fix (optional, can defer):** Remove `neuro: bool` and `evil: bool` fields, relying solely
on `singer_flags: dict[str, bool]`. Update `init_flags()` and any code that reads
`flags.neuro`/`flags.evil` to use `flags.singer_flags.get("neuro", False)` instead.

> This is risky and wide-reaching. Recommend deferring to Phase 8 unless it causes a concrete
> problem with a new project.

**Status:** Implemented 2026-09-08. Verified zero code reads `flags.neuro`/`flags.evil`
directly — all access already goes through `flags.singer_flags.get(artist.flag, False)`.
Removed the two bool fields from the dataclass; `db-check` and `check-group` both pass.

### 3d. `duet-group-name` default

`config.py:139`: `duet_group_name=p.get("duet-group-name", "Twins")`

The default `"Twins"` is Neuro-specific. For a project with a single singer, the duet group
name is irrelevant. For a project with two singers "Alice" and "Bob", it might be "AB Duet"
or whatever.

**Fix:** Make the default `None` (no duet group) and only set it if there are ≥2 artists:
```python
duet_group_name = p.get("duet-group-name")
if duet_group_name is None and len(artists) >= 2:
    duet_group_name = " & ".join(a.name for a in artists)  # or just the display-name
```
Or simply require it in the config for multi-artist projects (validate at load time).

### 3e. `_synthesized_project()` fallback

`config.py:_synthesized_project()` hardcodes the entire Neuro Twins project as a fallback
for configs without a `[project]` section. After Step 2, the Neuro project *always* has a
`[project]` section (it's in `projects/neuro/config.toml`), so this fallback is dead code
for that project.

**Options:**
- **Remove it** (preferred): every project must have a `[project]` section. Simplifies the
  code path.
- **Keep it** but rename to `_legacy_fallback()` and document it as a one-release transition
  aid.

Recommendation: **remove it** since we control all configs and the Neuro project now has an
explicit `[project]` section.

### 3f. `config.py` imports `from neuro import ...` in `_synthesized_project()`

If we keep the fallback (3e), this becomes `from ai_vt_singer import ...` or a relative
import. If we remove the fallback, this goes away entirely.

### 3g. `__init__.py` legacy constants

The deprecated module-level constants (`DATA_DIR`, `SONGS_CSV`, `SONGS_DB`, etc.) in
`__init__.py` are still imported by:
- `detection.py` (LOG_DIR, ROOT_DIR, UNOFFV3_EXTRA, UNOFFV3_DISC66)
- `file_tags.py` (IMAGES_COVERS_DIR, IMAGES_CUSTOM_DIR, LOG_DIR, ROOT_DIR)
- `utils.py` (COPYRIGHT_ISSUES_CSV, LOG_DIR, SETLISTS_DIR)
- `thumbnails.py` (DATES_OLD_CSV, FONT_PATH, LOG_DIR)
- `checks.py` (LOG_DIR, ROOT_DIR)
- `run.py` (LOG_DIR, UNOFFV3_EXTRA, UNOFFV3_DISC66)
- `_shortcuts.py` (LOG_DIR)

**Fix:** Migrate all remaining imports to use `get_project()` for paths. Then remove the
legacy constants from `__init__.py`. This is the "Phase 5 cleanup" that was deferred.

After this, `__init__.py` becomes just:
```python
"""AI VT Singer cover-artist formatting package."""
from .artists import CoverArtist, Project
from .config import load_project

_project: Project | None = None

def get_project() -> Project:
    global _project
    if _project is None:
        _project = load_project()
    return _project
```

### 3h. `metadata_utils/` location

Currently at the repo root, imported as a top-level package (`from metadata_utils import
engraver`). This works because PDM adds the repo root to `sys.path`. After the rename,
it's still fine. No action needed unless we want to move it under `ai_vt_singer/` (not
recommended — it's a separate concern).

### 3i. `neuro/.gitignore`

Check if this file exists and what's in it. If it has project-specific entries, move them
to the root `.gitignore` or `projects/neuro/.gitignore`.

---

## Step 4 — Update documentation

### 4a. `AGENTS.md`

- Update all `neuro/` path references to `ai_vt_singer/`
- Update the "Multi-project support" section to note that the Neuro Twins project now lives
  in `projects/neuro/`
- Update the test procedure to use `--project projects/neuro`
- Update the "Commands" table (entry points are now `ai_vt_singer.*`)
- Update the import examples

### 4b. `README.md`

- Update any references to the `neuro` package
- Update the project structure diagram
- Document that the Neuro Twins project is in `projects/neuro/`

### 4c. `projects/_template/README.md`

- Verify it still makes sense with the new layout

---

## Step 5 — Final verification

```bash
# From repo root
pdm install
pdm run ruff check ai_vt_singer/

# Full rebuild for the Neuro project
pdm run clear-db --project projects/neuro
pdm run update-json --project projects/neuro
# (manually review data/songs_new.json)
pdm run update-db --project projects/neuro
pdm run db-check --project projects/neuro

# Generation
pdm run songs-generate --project projects/neuro
pdm run albums-generate --project projects/neuro

# Thumbnails
pdm run thumbnails-generate --project projects/neuro

# Drive sync (dry run)
pdm run drive-push --project projects/neuro
```

Also verify `cd projects/neuro && pdm run db-check` works (PDM venv resolution walks up to
the repo root `pyproject.toml`).

---

## Risk Assessment

| Step | Risk | Mitigation |
|------|------|------------|
| 1 — Rename | Low (mechanical) | `git mv` + bulk import update + `ruff check` |
| 2 — Move files | Low (filesystem) | Verify with `--project` flag before committing |
| 3a — song_dirs | Medium (multiple call sites) | Add to Project first, then replace usages one at a time |
| 3b — arg_subdir | Low (2-3 call sites) | Simple constant → attribute |
| 3c — Flags cleanup | **High** | Defer; only do if a new project hits the issue |
| 3d — duet default | Low | Validate at config load |
| 3e — Remove fallback | Low | All configs now have `[project]` |
| 3g — Remove legacy constants | Medium (7 files) | Migrate one file at a time, run db-check after each |

**Recommended order:** 1 → 2 → 3a → 3b → 3e → 3g → 3d → 4 → 5 → (3c deferred)

---

## Effort Estimate

| Step | Est. effort |
|------|------------|
| 1 — Rename | 2–4 hours |
| 2 — Move files | 1–2 hours |
| 3 — Hardcoded assumptions | 1–2 days (3a/3b/3e/3g) |
| 4 — Docs | 2–4 hours |
| 5 — Verification | 2–4 hours |
| **Total** | **~3–5 days** |
