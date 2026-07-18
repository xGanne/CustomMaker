import os
import sys
from pathlib import Path

# Root of the project — works regardless of the working directory at launch time.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def app_data_dir():
    """Diretório para arquivos de estado (config, presets, cache, logs).

    Em modo dev: raiz do projeto (independente do cwd de lançamento).
    Empacotado (PyInstaller): %LOCALAPPDATA%/CustomMaker — o exe pode ser
    lançado de qualquer diretório sem espalhar arquivos (F19).
    """
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        path = Path(base) / "CustomMaker"
    else:
        path = _PROJECT_ROOT
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return str(path)


def app_data_path(relative_name):
    """Caminho absoluto para um arquivo/pasta de estado do aplicativo."""
    return str(Path(app_data_dir()) / relative_name)


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
