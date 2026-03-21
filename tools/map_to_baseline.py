from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.device_discovery import select_discovered_device
from engine.scaling import (
    BASELINE_DEVICE_LABEL,
    BASELINE_RESOLUTION,
    format_resolution,
    scale_xy,
)

# Usually you only need to edit POINTS, then run this file in IDE.
# If more than one adb device is connected, optionally set SERIAL.
SERIAL = None
POINTS = [
    (1500, 650),
    (1130, 835),
]


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


def main() -> int:
    device = _discover_current_device()
    src_resolution = tuple(device["target_resolution"])

    print(f"baseline_device: {BASELINE_DEVICE_LABEL}")
    print(f"connected_device: {device['device_label']}")
    print(f"serial: {device['serial']}")
    print(f"source_resolution: {format_resolution(src_resolution)}")
    print(f"target_resolution: {format_resolution(BASELINE_RESOLUTION)}")
    print("mapped_points:")
    for x, y in POINTS:
        mapped_x, mapped_y = scale_xy(
            x,
            y,
            src_resolution=src_resolution,
            dst_resolution=BASELINE_RESOLUTION,
        )
        print(f"  {x},{y} -> [{mapped_x}, {mapped_y}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
