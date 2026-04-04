from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Tuple


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def current_platform_dir() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def executable_name(stem: str) -> str:
    return f"{stem}.exe" if os.name == "nt" else stem


def find_bundled_binary(relative_root: str | Path, stem: str, search_root: Path | None = None) -> str | None:
    root = (search_root or project_root()) / Path(relative_root) / current_platform_dir()
    if not root.is_dir():
        return None

    filename = executable_name(stem)
    candidates = [root / filename]
    candidates.extend(sorted(root.glob(f"**/{filename}")))

    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.resolve()
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            continue
        if os.name != "nt" and not os.access(path, os.X_OK):
            continue
        return str(path)
    return None


def find_path_binary(stem: str) -> str | None:
    return shutil.which(stem)


def describe_adb_resolution() -> Tuple[str | None, str | None]:
    env_value = os.environ.get("ADB_BIN")
    if env_value:
        return env_value, "ADB_BIN"

    bundled = find_bundled_binary("third_party/platform-tools", "adb")
    if bundled:
        return bundled, "third_party/platform-tools"

    bundled_from_scrcpy = find_bundled_binary("third_party/scrcpy", "adb")
    if bundled_from_scrcpy:
        return bundled_from_scrcpy, "third_party/scrcpy"

    discovered = find_path_binary("adb")
    if discovered:
        return discovered, "PATH"

    return None, None


def describe_scrcpy_resolution() -> Tuple[str | None, str | None]:
    env_value = os.environ.get("SCRCPY_BIN")
    if env_value:
        return env_value, "SCRCPY_BIN"

    bundled = find_bundled_binary("third_party/scrcpy", "scrcpy")
    if bundled:
        return bundled, "third_party/scrcpy"

    discovered = find_path_binary("scrcpy")
    if discovered:
        return discovered, "PATH"

    return None, None


def describe_ffmpeg_resolution() -> Tuple[str | None, str | None]:
    env_value = os.environ.get("FFMPEG_BIN")
    if env_value:
        return env_value, "FFMPEG_BIN"

    discovered = find_path_binary("ffmpeg")
    if discovered:
        return discovered, "PATH"

    return None, None


def describe_ffprobe_resolution() -> Tuple[str | None, str | None]:
    env_value = os.environ.get("FFPROBE_BIN")
    if env_value:
        return env_value, "FFPROBE_BIN"

    discovered = find_path_binary("ffprobe")
    if discovered:
        return discovered, "PATH"

    return None, None


def adb_install_hint() -> str:
    platform_dir = current_platform_dir()
    if platform_dir == "macos":
        return (
            "Install adb with `brew install --cask android-platform-tools`, "
            "or place the official platform-tools package under "
            "`third_party/platform-tools/macos/`."
        )
    if platform_dir == "windows":
        return (
            "Install adb with Android Platform Tools, or place the official "
            "platform-tools package under `third_party/platform-tools/windows/`."
        )
    return (
        "Install adb with your system package manager, or place the official "
        "platform-tools package under `third_party/platform-tools/linux/`."
    )


def scrcpy_install_hint() -> str:
    platform_dir = current_platform_dir()
    if platform_dir == "macos":
        return (
            "Install scrcpy with `brew install scrcpy` and adb with "
            "`brew install --cask android-platform-tools`, or place the official "
            "scrcpy release under `third_party/scrcpy/macos/`."
        )
    if platform_dir == "windows":
        return (
            "Install scrcpy with `winget install --exact Genymobile.scrcpy`, "
            "or place the official scrcpy release under `third_party/scrcpy/windows/`."
        )
    return (
        "Install scrcpy with your system package manager, or place the official "
        "scrcpy release under `third_party/scrcpy/linux/`."
    )


def ffmpeg_install_hint() -> str:
    platform_dir = current_platform_dir()
    if platform_dir == "macos":
        return "Install ffmpeg with `brew install ffmpeg`, or set `FFMPEG_BIN` / `FFPROBE_BIN`."
    if platform_dir == "windows":
        return "Install ffmpeg and ensure `ffmpeg.exe` / `ffprobe.exe` are on PATH, or set `FFMPEG_BIN` / `FFPROBE_BIN`."
    return "Install ffmpeg with your system package manager, or set `FFMPEG_BIN` / `FFPROBE_BIN`."
