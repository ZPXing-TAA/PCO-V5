from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


def _normalize_alias(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _profile_aliases(profile: Dict[str, Any]) -> set[str]:
    aliases = {_normalize_alias(profile.get("device_id", ""))}
    device_label = profile.get("device_label")
    if device_label:
        aliases.add(_normalize_alias(str(device_label)))
    aliases.update(_normalize_alias(item) for item in profile.get("legacy_aliases", []))
    aliases.discard("")
    return aliases


def _discovered_aliases(discovered_device: Dict[str, Any]) -> set[str]:
    aliases = {_normalize_alias(str(discovered_device.get("device_id", "")))}
    device_label = discovered_device.get("device_label")
    if device_label:
        aliases.add(_normalize_alias(str(device_label)))
    manufacturer = discovered_device.get("manufacturer")
    model = discovered_device.get("model")
    if manufacturer and model:
        aliases.add(_normalize_alias(f"{manufacturer}_{model}"))
        aliases.add(_normalize_alias(f"{manufacturer} {model}"))
    aliases.discard("")
    return aliases


def iter_device_profiles(device_profiles_root: Path) -> Iterable[Dict[str, Any]]:
    if not device_profiles_root.is_dir():
        return []

    profiles = []
    for path in sorted(device_profiles_root.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            profile = json.load(handle)
        profile.setdefault("device_id", path.stem)
        profile["_path"] = str(path)
        profiles.append(profile)
    return profiles


def load_device_profile(device_profiles_root: Path, device_id: str) -> Optional[Dict[str, Any]]:
    profile_path = device_profiles_root / f"{device_id}.json"
    if not profile_path.is_file():
        return None
    with profile_path.open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    profile.setdefault("device_id", device_id)
    profile["_path"] = str(profile_path)
    return profile


def build_generated_device_profile(
    discovered_device: Dict[str, Any],
    total_configs_per_route: int = 80,
) -> Dict[str, Any]:
    device_id = str(discovered_device["device_id"])
    device_label = str(discovered_device["device_label"])
    target_resolution = tuple(discovered_device["target_resolution"])
    model_alias = _normalize_alias(
        f"{discovered_device.get('manufacturer', '')}_{discovered_device.get('model', '')}"
    )
    legacy_aliases = []
    if model_alias and model_alias not in {_normalize_alias(device_id), _normalize_alias(device_label)}:
        legacy_aliases.append(model_alias)

    return {
        "device_id": device_id,
        "device_label": device_label,
        "target_resolution": [int(target_resolution[0]), int(target_resolution[1])],
        "defaults": {
            "video_base": f"recordings/{device_id}",
            "total_configs_per_route": int(total_configs_per_route),
        },
        "legacy_aliases": legacy_aliases,
        "notes": "Auto-generated from ADB discovery. Adjust defaults if needed.",
    }


def save_device_profile(device_profiles_root: Path, profile: Dict[str, Any]) -> Dict[str, Any]:
    device_profiles_root.mkdir(parents=True, exist_ok=True)
    device_id = str(profile["device_id"])
    profile_path = device_profiles_root / f"{device_id}.json"
    payload = dict(profile)
    payload.pop("_path", None)
    with profile_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    payload["_path"] = str(profile_path)
    return payload


def ensure_device_profile(
    device_profiles_root: Path,
    discovered_device: Dict[str, Any],
    explicit_device_id: str | None = None,
    total_configs_per_route: int = 80,
) -> Tuple[Dict[str, Any], bool]:
    existing = find_matching_device_profile(
        device_profiles_root=device_profiles_root,
        discovered_device=discovered_device,
        explicit_device_id=explicit_device_id,
    )
    if existing is not None:
        return existing, False

    generated = build_generated_device_profile(
        discovered_device=discovered_device,
        total_configs_per_route=total_configs_per_route,
    )
    saved = save_device_profile(device_profiles_root, generated)
    return saved, True


def find_matching_device_profile(
    device_profiles_root: Path,
    discovered_device: Dict[str, Any],
    explicit_device_id: str | None = None,
) -> Optional[Dict[str, Any]]:
    if explicit_device_id:
        explicit_profile = load_device_profile(device_profiles_root, explicit_device_id)
        if explicit_profile is not None:
            return explicit_profile

    discovered_device_id = discovered_device["device_id"]
    exact_profile = load_device_profile(device_profiles_root, discovered_device_id)
    if exact_profile is not None:
        return exact_profile

    explicit_aliases = {_normalize_alias(explicit_device_id)} if explicit_device_id else set()
    explicit_aliases.discard("")
    discovered_aliases = _discovered_aliases(discovered_device)

    for profile in iter_device_profiles(device_profiles_root):
        aliases = _profile_aliases(profile)
        if explicit_aliases & aliases:
            return profile
        if discovered_aliases & aliases:
            return profile
    return None
