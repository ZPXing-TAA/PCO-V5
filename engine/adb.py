from __future__ import annotations

import os
import subprocess
from typing import Sequence

from engine.binary_resolver import adb_install_hint, describe_adb_resolution


def build_adb_command(*args: str, serial: str | None = None) -> list[str]:
    cmd = [resolve_adb_bin()]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    return cmd


def resolve_adb_bin() -> str:
    resolved, _source = describe_adb_resolution()
    if resolved:
        return resolved

    raise FileNotFoundError(
        "adb executable not found. Checked ADB_BIN, bundled `third_party/platform-tools`, "
        "bundled `third_party/scrcpy`, "
        f"and PATH. {adb_install_hint()}"
    )


def run_adb(
    *args: str,
    serial: str | None = None,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_adb_command(*args, serial=serial),
        check=check,
        capture_output=capture_output,
        text=True,
    )


def adb_text(*args: str, serial: str | None = None) -> str:
    completed = run_adb(*args, serial=serial, capture_output=True)
    return completed.stdout.strip()


def shell_input_tap(x: int, y: int, serial: str | None = None) -> None:
    run_adb("shell", "input", "tap", str(int(x)), str(int(y)), serial=serial, capture_output=True)


def shell_input_swipe(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int,
    serial: str | None = None,
) -> None:
    run_adb(
        "shell",
        "input",
        "swipe",
        str(int(x1)),
        str(int(y1)),
        str(int(x2)),
        str(int(y2)),
        str(int(duration_ms)),
        serial=serial,
        capture_output=True,
    )


def command_str(cmd: Sequence[str]) -> str:
    return " ".join(cmd)
