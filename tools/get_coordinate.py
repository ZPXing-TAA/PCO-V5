from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.adb import command_str, run_adb
from engine.device_discovery import select_discovered_device
from recording.scrcpy_recorder import resolve_scrcpy_bin

# Equivalent of the local "get cordinate.bat".
# Usually you only need to run this file in IDE.
# If more than one adb device is connected, optionally set SERIAL.
SERIAL = None
SCRCPY_EXTRA_ARGS: list[str] = []


def _discover_current_device():
    try:
        return select_discovered_device(serial=SERIAL)
    except RuntimeError as exc:
        message = str(exc)
        if "No connected adb device found" in message:
            raise SystemExit("No connected adb device found. Connect one device, then run again.") from exc
        if "Multiple connected devices detected" in message:
            raise SystemExit(
                "Multiple connected adb devices detected. Set SERIAL at the top of this file.\n"
                f"{message}"
            ) from exc
        raise SystemExit(message) from exc


def _set_pointer_location(enabled: bool, serial: str) -> None:
    run_adb(
        "shell",
        "settings",
        "put",
        "system",
        "pointer_location",
        "1" if enabled else "0",
        serial=serial,
        capture_output=True,
    )


def _build_scrcpy_command(serial: str) -> list[str]:
    cmd = [resolve_scrcpy_bin()]
    if serial:
        cmd.extend(["--serial", serial])
    cmd.extend(str(arg) for arg in SCRCPY_EXTRA_ARGS)
    return cmd


def main() -> int:
    device = _discover_current_device()
    serial = str(device["serial"])
    scrcpy_cmd = _build_scrcpy_command(serial)
    proc: subprocess.Popen[object] | None = None

    print(f"device: {device['device_label']}")
    print(f"serial: {serial}")
    print(f"scrcpy: {command_str(scrcpy_cmd)}")
    print("Enabling pointer_location...")
    _set_pointer_location(True, serial)

    try:
        print("Starting scrcpy...")
        proc = subprocess.Popen(scrcpy_cmd)
        return int(proc.wait())
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Ctrl+C received, closing scrcpy...")
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        return 130
    finally:
        print("Disabling pointer_location...")
        try:
            _set_pointer_location(False, serial)
        except Exception as exc:
            print(f"[WARN] Failed to restore pointer_location: {exc}")
        else:
            print("Done. System settings restored.")


if __name__ == "__main__":
    raise SystemExit(main())
