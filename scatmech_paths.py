from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent
_DATA_DIR_NAME: Final[str] = "DATA"
_SCATMECH_ENV_VAR: Final[str] = "SCATMECH_BIN"


def get_project_root() -> Path:
    return _PROJECT_ROOT


def get_data_dir(*, create: bool = False) -> Path:
    data_dir = _PROJECT_ROOT / _DATA_DIR_NAME
    if create:
        data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _default_scatmech_dirs() -> list[Path]:
    home = Path.home()
    if sys.platform.startswith("win"):
        candidates: list[Path] = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "SCATMECH")
        candidates.append(home / "SCATMECH")
        return candidates
    if sys.platform == "darwin":
        return [home / "Local" / "SCATMECH", home / ".local" / "share" / "SCATMECH"]
    return [home / ".local" / "share" / "SCATMECH", home / "SCATMECH"]


def get_scatmech_bin() -> Path:
    env_value = os.environ.get(_SCATMECH_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()

    defaults = _default_scatmech_dirs()
    for candidate in defaults:
        if candidate.is_dir():
            return candidate
    return defaults[0]


def configure_scatmech_path() -> Path:
    bin_dir = get_scatmech_bin()
    if not bin_dir.is_dir():
        return bin_dir

    bin_text = str(bin_dir)
    current_path = os.environ.get("PATH", "")
    entries = current_path.split(os.pathsep) if current_path else []
    if bin_text not in entries:
        os.environ["PATH"] = bin_text + os.pathsep + current_path if current_path else bin_text
    return bin_dir


def find_solver_executable(program: str) -> str | None:
    configure_scatmech_path()
    return shutil.which(program)


def format_missing_solver_message(program: str) -> str:
    bin_dir = get_scatmech_bin()
    return (
        f"[Error] '{program}' was not found.\n"
        "Set SCATMECH_BIN to the directory that contains the SCATMECH executables, "
        f"or add '{program}' to your PATH.\n"
        f"Checked SCATMECH_BIN directory: {bin_dir}"
    )
