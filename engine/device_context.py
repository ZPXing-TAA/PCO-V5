from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from engine.device_discovery import select_discovered_device
from engine.device_profiles import ensure_device_profile
from engine.scaling import (
    BASELINE_DEVICE_ID,
    BASELINE_DEVICE_LABEL,
    BASELINE_RESOLUTION,
    format_resolution,
    parse_resolution,
)


def _parse_int_list(raw_value: str | None) -> list[int] | None:
    if raw_value is None:
        return None
    text = raw_value.strip()
    if not text:
        return None
    values = []
    for token in text.split(","):
        item = token.strip()
        if not item:
            continue
        if not item.isdigit():
            raise ValueError(f"Expected comma-separated integers, got {raw_value!r}")
        values.append(int(item))
    return values


def _coerce_resolution(value: Any) -> tuple[int, int] | None:
    if value in (None, "", []):
        return None
    return parse_resolution(value)


def _build_defaults(scripts_root: Path) -> Dict[str, Any]:
    return {
        "config_root": os.environ.get("AUTO_CONFIG_ROOT", str(scripts_root / "render_configs")),
        "total_configs_per_route": 80,
    }


def _build_fallback_video_base(discovered_device: Dict[str, Any]) -> str:
    return str(Path("recordings") / str(discovered_device["device_id"]))


def _merge_defaults(
    base_defaults: Dict[str, Any],
    profile_defaults: Dict[str, Any] | None,
    override_defaults: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(base_defaults)
    if profile_defaults:
        filtered_profile_defaults = {
            key: value
            for key, value in profile_defaults.items()
            if key != "skip_route_suffixes"
        }
        merged.update(filtered_profile_defaults)
    for key, value in override_defaults.items():
        if value is not None:
            merged[key] = value
    merged["total_configs_per_route"] = int(merged.get("total_configs_per_route", 80))
    return merged


def build_runtime_device_context(
    project_root: str | Path | None = None,
    serial: str | None = None,
    explicit_device_id: str | None = None,
    target_resolution: str | Iterable[int] | None = None,
    video_base: str | None = None,
    config_root: str | None = None,
    total_configs_per_route: int | None = None,
    device_profiles_root: str | Path | None = None,
) -> Dict[str, Any]:
    scripts_root_path = Path(__file__).resolve().parents[1]
    project_root_path = Path(project_root or os.environ.get("AUTO_PROJECT_ROOT") or Path.cwd())
    profiles_root = Path(
        device_profiles_root
        or os.environ.get("AUTO_DEVICE_PROFILES_ROOT")
        or scripts_root_path / "device_profiles"
    )

    env_serial = os.environ.get("AUTO_SERIAL")
    env_device_id = os.environ.get("AUTO_DEVICE_ID")
    env_target_resolution = os.environ.get("AUTO_TARGET_RESOLUTION")
    env_video_base = os.environ.get("AUTO_VIDEO_BASE")
    env_config_root = os.environ.get("AUTO_CONFIG_ROOT")
    env_total_configs = os.environ.get("AUTO_TOTAL_CONFIGS_PER_ROUTE")
    resolved_total_configs = (
        total_configs_per_route
        if total_configs_per_route is not None
        else (int(env_total_configs) if env_total_configs else 80)
    )

    discovered_device = select_discovered_device(serial=serial or env_serial)
    device_profile, device_profile_created = ensure_device_profile(
        device_profiles_root=profiles_root,
        discovered_device=discovered_device,
        explicit_device_id=explicit_device_id or env_device_id,
        total_configs_per_route=resolved_total_configs,
    )

    profile_defaults = dict((device_profile or {}).get("defaults", {}))
    profile_target_resolution = _coerce_resolution((device_profile or {}).get("target_resolution"))

    override_target_resolution = _coerce_resolution(target_resolution or env_target_resolution)
    resolved_target_resolution = (
        override_target_resolution
        or profile_target_resolution
        or tuple(discovered_device["target_resolution"])
    )

    override_defaults: Dict[str, Any] = {
        "video_base": video_base or env_video_base,
        "config_root": config_root or env_config_root,
        "total_configs_per_route": total_configs_per_route
        if total_configs_per_route is not None
        else (int(env_total_configs) if env_total_configs else None),
    }
    defaults = _merge_defaults(
        base_defaults=_build_defaults(scripts_root_path),
        profile_defaults=profile_defaults,
        override_defaults=override_defaults,
    )
    if not defaults.get("video_base"):
        defaults["video_base"] = _build_fallback_video_base(discovered_device)

    runtime_device_context: Dict[str, Any] = {
        "serial": discovered_device["serial"],
        "device_id": (device_profile or {}).get("device_id") or discovered_device["device_id"],
        "device_label": (device_profile or {}).get("device_label") or discovered_device["device_label"],
        "manufacturer": discovered_device["manufacturer"],
        "model": discovered_device["model"],
        "baseline_device_id": BASELINE_DEVICE_ID,
        "baseline_device_label": BASELINE_DEVICE_LABEL,
        "baseline_resolution": BASELINE_RESOLUTION,
        "target_resolution": resolved_target_resolution,
        "target_resolution_text": format_resolution(resolved_target_resolution),
        "defaults": defaults,
        "discovered_device": discovered_device,
        "device_profile": device_profile,
        "device_profile_created": device_profile_created,
        "device_profiles_root": str(profiles_root),
        "project_root": str(project_root_path),
        "scripts_root": str(scripts_root_path),
    }
    return runtime_device_context
