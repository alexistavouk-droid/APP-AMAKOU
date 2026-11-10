"""Chemins de l'application (source ou exécutable PyInstaller)."""
import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    """Dossier modifiable : à côté du .exe une fois figé, racine du projet sinon."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parent.parent


def user_dir(name: str) -> Path:
    d = app_dir() / name
    if not d.exists():
        d.mkdir(parents=True, exist_ok=True)
        src = bundled_dir() / name
        if src.exists() and src != d:
            for f in src.glob("*.json"):
                shutil.copy(f, d / f.name)
    return d
