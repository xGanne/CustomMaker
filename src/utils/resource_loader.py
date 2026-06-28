import sys
from pathlib import Path

# Root of the project — works regardless of the working directory at launch time.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def resource_path(relative_path):
    """Return absolute path to a resource, compatible with dev mode and PyInstaller."""
    try:
        # PyInstaller bundles assets into a temp folder stored in sys._MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        base_path = _PROJECT_ROOT

    candidate = base_path / relative_path
    if candidate.exists():
        return str(candidate)

    assets_candidate = base_path / "assets" / relative_path
    if assets_candidate.exists():
        return str(assets_candidate)

    return str(candidate)
