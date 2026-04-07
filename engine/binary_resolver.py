from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Tuple

if os.name == "nt":
    import winreg


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


def read_persistent_env_var(name: str) -> str | None:
    if os.name != "nt":
        return None

    registry_locations = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    )
    for hive, subkey in registry_locations:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _value_type = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            continue
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_env_override(name: str) -> str | None:
    env_value = os.environ.get(name)
    if env_value and env_value.strip():
        return env_value.strip()
    return read_persistent_env_var(name)


def find_sibling_binary(explicit_binary: str, sibling_stem: str) -> str | None:
    parent = Path(explicit_binary).expanduser().parent
    candidate = parent / executable_name(sibling_stem)
    if not candidate.is_file():
        return None
    if os.name != "nt" and not os.access(candidate, os.X_OK):
        return None
    return str(candidate)


def describe_adb_resolution() -> Tuple[str | None, str | None]:
    env_value = resolve_env_override("ADB_BIN")
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
    env_value = resolve_env_override("SCRCPY_BIN")
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
    env_value = resolve_env_override("FFMPEG_BIN")
    if env_value:
        return env_value, "FFMPEG_BIN"

    sibling_from_ffprobe = resolve_env_override("FFPROBE_BIN")
    if sibling_from_ffprobe:
        sibling = find_sibling_binary(sibling_from_ffprobe, "ffmpeg")
        if sibling:
            return sibling, "FFPROBE_BIN sibling"

    bundled = find_bundled_binary("third_party/ffmpeg", "ffmpeg")
    if bundled:
        return bundled, "third_party/ffmpeg"

    discovered = find_path_binary("ffmpeg")
    if discovered:
        return discovered, "PATH"

    return None, None


def describe_ffprobe_resolution() -> Tuple[str | None, str | None]:
    env_value = resolve_env_override("FFPROBE_BIN")
    if env_value:
        return env_value, "FFPROBE_BIN"

    sibling_from_ffmpeg = resolve_env_override("FFMPEG_BIN")
    if sibling_from_ffmpeg:
        sibling = find_sibling_binary(sibling_from_ffmpeg, "ffprobe")
        if sibling:
            return sibling, "FFMPEG_BIN sibling"

    bundled = find_bundled_binary("third_party/ffmpeg", "ffprobe")
    if bundled:
        return bundled, "third_party/ffmpeg"

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
        return (
            "Install ffmpeg with `brew install ffmpeg`, place an official build under "
            "`third_party/ffmpeg/macos/`, or set `FFMPEG_BIN` / `FFPROBE_BIN`."
        )
    if platform_dir == "windows":
        return (
            "Install ffmpeg and ensure `ffmpeg.exe` / `ffprobe.exe` are on PATH, place an official build under "
            "`third_party/ffmpeg/windows/`, or set `FFMPEG_BIN` / `FFPROBE_BIN`."
        )
    return (
        "Install ffmpeg with your system package manager, place an official build under "
        "`third_party/ffmpeg/linux/`, or set `FFMPEG_BIN` / `FFPROBE_BIN`."
    )
