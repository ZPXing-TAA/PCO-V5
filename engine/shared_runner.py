from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from config.switcher import apply_render_config
from engine.route_segments import (
    RouteSegment,
    build_route_segments,
    cleanup_route_outputs,
    segment_video_path,
    validate_expected_videos,
)
from engine.runner import build_action_table, run_route
from engine.scaling import BASELINE_RESOLUTION, scale_xy
from recording.recorder import Recorder

DEFAULT_STEP_DELAY = 0.4
DEFAULT_ROUTE_GAP = 1.0
DEFAULT_RECORD_START_SETTLE_SEC = float(os.environ.get("AUTO_RECORD_START_SETTLE_SEC", "0.3"))


def default_route_root() -> Path:
    return Path(__file__).resolve().parents[1] / "routes" / "natlan"


def parse_route_suffix_list(raw_value: str | None) -> Optional[List[int]]:
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
            raise ValueError(f"Expected comma-separated route suffixes, got {raw_value!r}")
        values.append(int(item))
    return values


def resolve_skip_route_suffixes(extra_skip_route_suffixes: Sequence[int] | None = None) -> List[int]:
    resolved = set()
    env_skip_route_suffixes = parse_route_suffix_list(os.environ.get("AUTO_SKIP_ROUTE_SUFFIXES"))
    for source in (env_skip_route_suffixes, extra_skip_route_suffixes):
        if source:
            resolved.update(int(item) for item in source)
    return sorted(resolved)


def load_route_module(route_root: Path, route_suffix: int):
    route_path = route_root / f"{route_suffix}.py"
    module_name = f"{route_root.name}_route_{route_suffix}"
    spec = importlib.util.spec_from_file_location(module_name, route_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load route module from {route_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_route_suffixes(route_root: Path) -> List[int]:
    suffixes = []
    for path in route_root.glob("*.py"):
        if path.stem.isdigit():
            suffixes.append(int(path.stem))
    return sorted(suffixes)


def resolve_route_window(
    route_suffixes: Sequence[int],
    start_from: int | None = None,
    end_at: int | None = None,
) -> List[int]:
    selected = list(route_suffixes)
    if start_from is not None and start_from not in selected:
        raise ValueError(f"START_FROM_ROUTE={start_from} not in active routes: {selected}")
    if end_at is not None and end_at not in selected:
        raise ValueError(f"END_AT_ROUTE={end_at} not in active routes: {selected}")
    if start_from is not None and end_at is not None and start_from > end_at:
        raise ValueError("START_FROM_ROUTE must be <= END_AT_ROUTE.")
    if start_from is not None:
        selected = [suffix for suffix in selected if suffix >= start_from]
    if end_at is not None:
        selected = [suffix for suffix in selected if suffix <= end_at]
    return selected


def build_portal(portal_xy: Sequence[int], runtime_device_context: Mapping[str, object]) -> List[int]:
    target_resolution = tuple(runtime_device_context["target_resolution"])
    x, y = scale_xy(
        int(portal_xy[0]),
        int(portal_xy[1]),
        src_resolution=BASELINE_RESOLUTION,
        dst_resolution=target_resolution,
    )
    return [x, y]


def collect_configs(root_folder: str | Path, limit: int) -> List[Tuple[str, str]]:
    root = Path(root_folder)
    picked: List[Tuple[str, str]] = []
    for resolution_dir in sorted(root.iterdir()):
        if not resolution_dir.is_dir():
            continue
        for json_path in sorted(resolution_dir.glob("*.json")):
            config_id = json_path.stem
            picked.append((str(json_path), config_id))
            if len(picked) >= limit:
                return picked
    return picked


def collect_configs_in_order(root_folder: str | Path, config_ids: Sequence[str]) -> List[Tuple[str, str]]:
    root = Path(root_folder)
    config_index: dict[str, str] = {}

    for resolution_dir in sorted(root.iterdir()):
        if not resolution_dir.is_dir():
            continue
        for json_path in sorted(resolution_dir.glob("*.json")):
            config_id = json_path.stem
            if config_id in config_index:
                raise ValueError(f"Duplicate config id found under {root}: {config_id}")
            config_index[config_id] = str(json_path)

    picked: List[Tuple[str, str]] = []
    missing: List[str] = []
    for config_id in config_ids:
        json_path = config_index.get(config_id)
        if json_path is None:
            missing.append(config_id)
            continue
        picked.append((json_path, config_id))

    if missing:
        raise ValueError(
            f"Config ids not found under {root}: {missing}"
        )

    return picked


def print_runtime_device_context(runtime_device_context: Mapping[str, object]) -> None:
    print("[DEVICE] serial:", runtime_device_context["serial"])
    print("[DEVICE] device_label:", runtime_device_context["device_label"])
    print("[DEVICE] device_id:", runtime_device_context["device_id"])
    print("[DEVICE] target_resolution:", runtime_device_context["target_resolution_text"])


def _country_from_route_root(route_root: Path) -> str:
    return route_root.name.split("_", 1)[0]


def _prepare_route_recorders(
    video_base: str,
    config_id: str,
    segments: Sequence[RouteSegment],
    serial: str,
    record_start_settle_sec: float,
):
    recorder: Recorder | None = None

    def on_record_start(segment_index: int) -> None:
        nonlocal recorder
        if segment_index >= len(segments):
            raise ValueError("record_start count does not match precomputed route segments.")
        segment = segments[segment_index]
        video_path = segment_video_path(video_base, config_id, segment)
        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        if recorder is not None:
            recorder.stop()
        recorder = Recorder(video_path, serial=serial)
        recorder.start()
        time.sleep(record_start_settle_sec)

    def on_record_stop(_: int) -> None:
        nonlocal recorder
        if recorder is not None:
            recorder.stop()
            recorder = None

    def stop_any() -> None:
        nonlocal recorder
        if recorder is not None:
            recorder.stop()
            recorder = None

    return on_record_start, on_record_stop, stop_any


def run_multiroute_workflow(
    runtime_device_context: Mapping[str, object],
    route_root: str | Path | None = None,
    route_suffixes: Sequence[int] | None = None,
    skip_route_suffixes: Sequence[int] | None = None,
    config_ids: Sequence[str] | None = None,
    start_from_route: int | None = None,
    end_at_route: int | None = None,
    step_delay: float = DEFAULT_STEP_DELAY,
    route_gap: float = DEFAULT_ROUTE_GAP,
    record_start_settle_sec: float = DEFAULT_RECORD_START_SETTLE_SEC,
    enable_recording: bool = True,
    use_next_portal_on_last_config: bool = True,
) -> None:
    route_root_path = Path(route_root or default_route_root())
    defaults = dict(runtime_device_context["defaults"])
    selected_route_suffixes = list(route_suffixes or discover_route_suffixes(route_root_path))
    if not selected_route_suffixes:
        raise ValueError("No route suffix found.")

    selected_route_suffixes = resolve_route_window(
        route_suffixes=selected_route_suffixes,
        start_from=start_from_route,
        end_at=end_at_route,
    )
    resolved_skip_route_suffixes = set(resolve_skip_route_suffixes(skip_route_suffixes))
    if resolved_skip_route_suffixes:
        selected_route_suffixes = [
            suffix for suffix in selected_route_suffixes if suffix not in resolved_skip_route_suffixes
        ]
        print(f"[INFO] Skip routes: {sorted(resolved_skip_route_suffixes)}")
    if not selected_route_suffixes:
        raise ValueError("No route suffix left after route window and skip filter.")

    if config_ids is None:
        configs = collect_configs(defaults["config_root"], defaults["total_configs_per_route"])
    else:
        configs = collect_configs_in_order(defaults["config_root"], config_ids)
    if not configs:
        raise ValueError(f"No config json found under {defaults['config_root']}.")

    action_table = build_action_table(runtime_device_context)
    if enable_recording:
        os.makedirs(defaults["video_base"], exist_ok=True)
    print_runtime_device_context(runtime_device_context)
    print(f"[INFO] Route list: {selected_route_suffixes}")
    print(f"[INFO] Config count per route: {len(configs)}")
    print(f"[INFO] Recording: {'enabled' if enable_recording else 'disabled'}")
    if config_ids is not None:
        print(f"[INFO] Config order: {list(config_ids)}")

    country = _country_from_route_root(route_root_path)

    for route_index, route_suffix in enumerate(selected_route_suffixes):
        route_module = load_route_module(route_root_path, route_suffix)
        route = route_module.ROUTE
        current_portal = build_portal(route_module.PORTAL, runtime_device_context)
        next_portal_raw = getattr(route_module, "NEXT_PORTAL", None)
        next_portal = build_portal(next_portal_raw, runtime_device_context) if next_portal_raw else None

        segments = build_route_segments(route, country, route_suffix)
        config_ids = [config_id for _, config_id in configs]
        transitioned_in_last_run = False

        print(f"\n[ROUTE] Start route {route_suffix}")
        print(f"[ROUTE] Current portal: {current_portal}")
        if next_portal is not None:
            print(f"[ROUTE] Next portal: {next_portal}")
        print(f"[ROUTE] Segment count: {len(segments)}")
        if not enable_recording and segments:
            print(f"[ROUTE] Recording disabled; {len(segments)} record segments will be skipped.")

        if enable_recording:
            cleanup_route_outputs(defaults["video_base"], segments)
        if enable_recording and segments:
            print(f"[ROUTE] Cleared stable outputs for route {route_suffix}.")

        for config_index, (json_path, config_id) in enumerate(configs, start=1):
            print(f"[CONFIG][R{route_suffix}][{config_index}/{len(configs)}] {json_path}")
            if config_index > 1 and (config_index - 1) % 3 == 0:
                if "adjust_game_time" in action_table:
                    print(f"[TIME][R{route_suffix}] adjust before config #{config_index}")
                    action_table["adjust_game_time"]()
                else:
                    print("[WARN] adjust_game_time not available in current action table.")

            apply_render_config(json_path, runtime_device_context)
            teleport_target = (
                next_portal
                if (
                    use_next_portal_on_last_config
                    and config_index == len(configs)
                    and next_portal is not None
                )
                else current_portal
            )
            if enable_recording:
                on_record_start, on_record_stop, stop_any = _prepare_route_recorders(
                    video_base=defaults["video_base"],
                    config_id=config_id,
                    segments=segments,
                    serial=str(runtime_device_context["serial"]),
                    record_start_settle_sec=record_start_settle_sec,
                )
                skip_record_actions = False
            else:
                on_record_start = None
                on_record_stop = None

                def stop_any() -> None:
                    return None

                skip_record_actions = True
            try:
                result = run_route(
                    route=route,
                    action_table=action_table,
                    step_delay=step_delay,
                    current_portal=current_portal,
                    teleport_portal=teleport_target,
                    on_record_start=on_record_start,
                    on_record_stop=on_record_stop,
                    skip_record_actions=skip_record_actions,
                )
            finally:
                stop_any()

            if result["record_starts_seen"] != len(segments):
                raise ValueError(
                    f"Route {route_suffix} consumed {result['record_starts_seen']} record_start actions, "
                    f"expected {len(segments)}."
                )
            if config_index == len(configs) and teleport_target == next_portal and result["teleport_used"]:
                transitioned_in_last_run = True

        if enable_recording:
            missing = validate_expected_videos(config_ids, defaults["video_base"], segments)
            if missing:
                preview = ", ".join(missing[:3])
                print(
                    f"[WARN] Route {route_suffix} completed but missing {len(missing)} expected videos. "
                    f"Examples: {preview}"
                )
            else:
                print(f"[ROUTE] Finished route {route_suffix} ({len(configs)}/{len(configs)})")
        else:
            print(f"[ROUTE] Finished route {route_suffix} without recording ({len(configs)}/{len(configs)})")

        if route_index < len(selected_route_suffixes) - 1:
            if next_portal is None:
                raise ValueError(
                    f"Route {route_suffix} has no NEXT_PORTAL. "
                    "Please add NEXT_PORTAL = [x, y] in this route file."
                )
            if transitioned_in_last_run:
                print(
                    f"[TRANSITION] Route {route_suffix} already moved to NEXT_PORTAL "
                    "during last config run."
                )
            else:
                print(f"[TRANSITION] Route {route_suffix} -> next route via NEXT_PORTAL {next_portal}")
                action_table["teleport"](next_portal)
                time.sleep(route_gap)


def run_debug_multiroute_workflow(
    runtime_device_context: Mapping[str, object],
    route_root: str | Path | None = None,
    route_suffixes: Sequence[int] | None = None,
    skip_route_suffixes: Sequence[int] | None = None,
    start_from_route: int | None = None,
    end_at_route: int | None = None,
    step_delay: float = DEFAULT_STEP_DELAY,
    route_gap: float = DEFAULT_ROUTE_GAP,
) -> None:
    route_root_path = Path(route_root or default_route_root())
    selected_route_suffixes = list(route_suffixes or discover_route_suffixes(route_root_path))
    if not selected_route_suffixes:
        raise ValueError("No route suffix found.")

    selected_route_suffixes = resolve_route_window(
        route_suffixes=selected_route_suffixes,
        start_from=start_from_route,
        end_at=end_at_route,
    )
    resolved_skip_route_suffixes = set(resolve_skip_route_suffixes(skip_route_suffixes))
    if resolved_skip_route_suffixes:
        selected_route_suffixes = [
            suffix for suffix in selected_route_suffixes if suffix not in resolved_skip_route_suffixes
        ]
        print(f"[INFO] Skip routes: {sorted(resolved_skip_route_suffixes)}")
    if not selected_route_suffixes:
        raise ValueError("No route suffix left after route window and skip filter.")
    action_table = build_action_table(runtime_device_context)
    print_runtime_device_context(runtime_device_context)
    print(f"[INFO] Route range: {selected_route_suffixes} (folder: {route_root_path.name})")

    for route_index, route_suffix in enumerate(selected_route_suffixes):
        route_module = load_route_module(route_root_path, route_suffix)
        route = route_module.ROUTE
        next_portal_raw = getattr(route_module, "NEXT_PORTAL", None)
        if next_portal_raw is None:
            raise ValueError(
                f"Route {route_suffix} has no NEXT_PORTAL. "
                "Please add NEXT_PORTAL=[x, y] in this route file."
            )
        next_portal = build_portal(next_portal_raw, runtime_device_context)
        print(f"\n[ROUTE] Start route {route_suffix}")
        run_route(
            route=route,
            action_table=action_table,
            step_delay=step_delay,
            skip_record_actions=True,
            skip_in_route_teleport=True,
        )
        print(f"[TRANSITION] Route {route_suffix} -> next via NEXT_PORTAL {next_portal}")
        action_table["teleport"](next_portal)
        if route_index < len(selected_route_suffixes) - 1:
            time.sleep(route_gap)


def run_test_route_workflow(
    runtime_device_context: Mapping[str, object],
    route_suffix: int,
    test_mode: str,
    route_root: str | Path | None = None,
    skip_teleport: bool = False,
    step_delay: float = DEFAULT_STEP_DELAY,
) -> None:
    route_root_path = Path(route_root or default_route_root())
    route_module = load_route_module(route_root_path, route_suffix)
    route = route_module.ROUTE
    current_portal = build_portal(route_module.PORTAL, runtime_device_context)
    next_portal_raw = getattr(route_module, "NEXT_PORTAL", None)
    next_portal = build_portal(next_portal_raw, runtime_device_context) if next_portal_raw else None

    action_table = build_action_table(runtime_device_context)
    print_runtime_device_context(runtime_device_context)

    if test_mode == "single":
        print(f"[TEST] Run route {route_suffix} with current portal: {current_portal}")
        run_route(
            route=route,
            action_table=action_table,
            step_delay=step_delay,
            current_portal=current_portal,
            skip_record_actions=True,
            skip_in_route_teleport=skip_teleport,
        )
        return

    if test_mode != "current_next":
        raise ValueError(f"Unknown test mode: {test_mode}")
    if next_portal is None:
        raise ValueError(f"Route {route_suffix} has no NEXT_PORTAL. Please fill NEXT_PORTAL in route file.")

    print(f"[TEST] Run #1 route {route_suffix} with current portal: {current_portal}")
    run_route(
        route=route,
        action_table=action_table,
        step_delay=step_delay,
        current_portal=current_portal,
        skip_record_actions=True,
        skip_in_route_teleport=skip_teleport,
    )

    print(f"[TEST] Run #2 route {route_suffix} with NEXT_PORTAL: {next_portal}")
    run_route(
        route=route,
        action_table=action_table,
        step_delay=step_delay,
        current_portal=next_portal,
        skip_record_actions=True,
        skip_in_route_teleport=skip_teleport,
    )
