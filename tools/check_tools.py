from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.binary_resolver import (
    adb_install_hint,
    current_platform_dir,
    describe_adb_resolution,
    describe_ffmpeg_resolution,
    describe_ffprobe_resolution,
    describe_scrcpy_resolution,
    ffmpeg_install_hint,
    project_root,
    scrcpy_install_hint,
)


def _print_result(name: str, resolved_path: str | None, source: str | None, hint: str) -> bool:
    if resolved_path:
        print(f"[OK] {name}")
        print(f"  source: {source}")
        print(f"  path:   {resolved_path}")
        return True

    print(f"[MISSING] {name}")
    print("  source: not found")
    print(f"  fix:    {hint}")
    return False


def main() -> int:
    platform_dir = current_platform_dir()
    root = project_root()

    print("Tool check")
    print(f"platform: {platform_dir}")
    print(f"project:  {root}")
    print(f"bundle:   {root / 'third_party'}")
    print()

    adb_path, adb_source = describe_adb_resolution()
    scrcpy_path, scrcpy_source = describe_scrcpy_resolution()
    ffmpeg_path, ffmpeg_source = describe_ffmpeg_resolution()
    ffprobe_path, ffprobe_source = describe_ffprobe_resolution()

    adb_ok = _print_result("adb", adb_path, adb_source, adb_install_hint())
    print()
    scrcpy_ok = _print_result("scrcpy", scrcpy_path, scrcpy_source, scrcpy_install_hint())
    print()
    ffmpeg_ok = _print_result("ffmpeg", ffmpeg_path, ffmpeg_source, ffmpeg_install_hint())
    print()
    ffprobe_ok = _print_result("ffprobe", ffprobe_path, ffprobe_source, ffmpeg_install_hint())

    print()
    if adb_ok and scrcpy_ok and ffmpeg_ok and ffprobe_ok:
        print("Ready: adb, scrcpy, ffmpeg, and ffprobe are all available.")
        return 0

    print("Not ready: install missing tools globally or place official releases under third_party/.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
