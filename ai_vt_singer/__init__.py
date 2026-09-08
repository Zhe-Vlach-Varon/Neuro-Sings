"""AI VT Singer cover-artist formatting package."""

from .artists import CoverArtist as CoverArtist
from .artists import Project as Project
from .config import load_project as load_project

_project: Project | None = None


def get_project() -> Project:
    """Return the active :class:`Project`, loading and caching it on first use.

    The project is read from ``config.toml`` in the current working directory (see
    :func:`ai_vt_singer.config.load_project`), so selecting a project is simply a matter of
    ``cd``-ing into that project's directory.
    """
    global _project
    if _project is None:
        _project = load_project()
    return _project
