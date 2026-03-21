from __future__ import annotations

import re
from typing import Any, Dict, List

from engine.adb import adb_text, command_str, run_adb
from engine.scaling import format_resolution, normalize_landscape_resolution


def _normalize_identity_token(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "unknown"


def _clean_prop(value: str, fallback: str) -> str:
    cleaned = value.replace("\r", "").strip()
    return cleaned or fallback


def make_device_label(manufacturer: str, model: str) -> str:
    manufacturer = _clean_prop(manufacturer, "Unknown")
    model = _clean_prop(model, "Unknown")
    return f"{manufacturer} {model}".strip()


def make_device_id(manufacturer: str, model: str, resolution: tuple[int, int]) -> str:
    brand = _normalize_identity_token(manufacturer)
    model_token = _normalize_identity_token(model)
    return f"{brand}_{model_token}_{int(resolution[0])}x{int(resolution[1])}"


def parse_wm_size(raw_output: str) -> tuple[int, int]:
    override_match = re.search(r"Override size:\s*(\d+)\s*x\s*(\d+)", raw_output, flags=re.IGNORECASE)
    physical_match = re.search(r"Physical size:\s*(\d+)\s*x\s*(\d+)", raw_output, flags=re.IGNORECASE)
    generic_match = re.search(r"(\d+)\s*x\s*(\d+)", raw_output)
    match = override_match or physical_match or generic_match
    if match is None:
        raise ValueError(f"Failed to parse wm size output: {raw_output!r}")
    return normalize_landscape_resolution(int(match.group(1)), int(match.group(2)))


def list_connected_serials() -> List[str]:
    completed = run_adb("devices", "-l", capture_output=True)
    serials: List[str] = []
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices attached"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if state == "device":
            serials.append(serial)
    return serials


def discover_device(serial: str) -> Dict[str, Any]:
    manufacturer = _clean_prop(
        adb_text("shell", "getprop", "ro.product.manufacturer", serial=serial),
        "Unknown",
    )
    model = _clean_prop(
        adb_text("shell", "getprop", "ro.product.model", serial=serial),
        "Unknown",
    )
    raw_resolution = adb_text("shell", "wm", "size", serial=serial)
    resolution = parse_wm_size(raw_resolution)
    device_label = make_device_label(manufacturer, model)
    device_id = make_device_id(manufacturer, model, resolution)
    discovered_device: Dict[str, Any] = {
        "serial": serial,
        "manufacturer": manufacturer,
        "model": model,
        "device_label": device_label,
        "device_id": device_id,
        "resolution": resolution,
        "target_resolution": resolution,
        "resolution_text": format_resolution(resolution),
    }
    return discovered_device


def discover_connected_devices() -> List[Dict[str, Any]]:
    return [discover_device(serial) for serial in list_connected_serials()]


def select_discovered_device(serial: str | None = None) -> Dict[str, Any]:
    serials = list_connected_serials()
    if serial:
        if serial not in serials:
            raise RuntimeError(
                f"Requested AUTO_SERIAL/--serial {serial!r} is not connected. "
                f"Connected serials: {serials or 'none'}"
            )
        return discover_device(serial)

    if not serials:
        raise RuntimeError(
            f"No connected adb device found. Checked via `{command_str(['adb', 'devices', '-l'])}`."
        )

    if len(serials) == 1:
        return discover_device(serials[0])

    candidates = discover_connected_devices()
    candidate_lines = [
        f"- {item['serial']} | {item['device_label']}"
        for item in candidates
    ]
    joined = "\n".join(candidate_lines)
    raise RuntimeError(
        "Multiple connected devices detected. Set AUTO_SERIAL or pass --serial.\n"
        f"{joined}"
    )
