from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _normalize_alias(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


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

    explicit_alias = _normalize_alias(explicit_device_id) if explicit_device_id else None
    discovered_alias = _normalize_alias(discovered_device_id)

    for profile in iter_device_profiles(device_profiles_root):
        aliases = {_normalize_alias(profile.get("device_id", ""))}
        aliases.update(_normalize_alias(item) for item in profile.get("legacy_aliases", []))
        if explicit_alias and explicit_alias in aliases:
            return profile
        if discovered_alias in aliases:
            return profile
    return None
