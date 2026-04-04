from __future__ import annotations

import importlib.util
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Iterable, List, Mapping, Optional, Sequence, Tuple

from config.switcher import apply_render_config
from engine.route_segments import (
    RouteSegment,
    build_route_segments,
    build_split_plan_stats,
    cleanup_route_outputs,
    raw_segment_video_path,
    validate_expected_videos,
)
from engine.runner import build_action_table, run_route
from engine.scaling import BASELINE_RESOLUTION, scale_xy
from engine.video_postprocess import DEFAULT_SHORTFALL_TOLERANCE_SEC, process_segment_directory
from recording.recorder import Recorder

DEFAULT_STEP_DELAY = 0.4
DEFAULT_ROUTE_GAP = 1.0
DEFAULT_RECORD_START_SETTLE_SEC = float(os.environ.get("AUTO_RECORD_START_SETTLE_SEC", "0.3"))
DEFAULT_VIDEO_POSTPROCESS_MODE = os.environ.get("AUTO_VIDEO_POSTPROCESS_MODE", "apply").strip().lower()
DEFAULT_VIDEO_POSTPROCESS_WORKERS = int(os.environ.get("AUTO_VIDEO_POSTPROCESS_WORKERS", "1"))
ALLOWED_ROUTE_SUBPATHS = ("natlan", "mondstadt")
ROUTES_ROOT = Path(__file__).resolve().parents[1] / "routes"


def default_route_root() -> Path:
    return ROUTES_ROOT / "natlan"


def resolve_route_root(route_subpath: str | None = None) -> Path:
    selected = (route_subpath or "natlan").strip().lower()
    if selected not in ALLOWED_ROUTE_SUBPATHS:
        allowed = ", ".join(ALLOWED_ROUTE_SUBPATHS)
        raise ValueError(
            f"route_subpath must be one of: {allowed}. Got {route_subpath!r}."
        )
    return ROUTES_ROOT / selected


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
    discovered_device = runtime_device_context.get("discovered_device", {}) or {}
    device_profile = runtime_device_context.get("device_profile", {}) or {}
    device_profile_created = bool(runtime_device_context.get("device_profile_created"))
    print("[DEVICE] serial:", runtime_device_context["serial"])
    print("[DEVICE] device_label:", runtime_device_context["device_label"])
    print("[DEVICE] device_id:", runtime_device_context["device_id"])
    print("[DEVICE] target_resolution:", runtime_device_context["target_resolution_text"])
    if discovered_device:
        print("[DEVICE] discovered_resolution:", discovered_device.get("resolution_text"))
        print("[DEVICE] discovered_device_id:", discovered_device.get("device_id"))
    print("[DEVICE] device_profile:", device_profile.get("_path") if device_profile else "none")
    if device_profile_created:
        print("[DEVICE] device_profile_created:", True)


def resolve_video_postprocess_mode(postprocess_mode: str) -> str:
    resolved = postprocess_mode.strip().lower()
    if resolved not in {"apply", "dry-run"}:
        raise ValueError("video postprocess mode must be 'apply' or 'dry-run'.")
    return resolved


def _country_from_route_root(route_root: Path) -> str:
    return route_root.name.split("_", 1)[0]


def _wait_for_postprocess_jobs(route_suffix: int, jobs: Sequence[Tuple[RouteSegment, Future]]) -> None:
    for segment, future in jobs:
        try:
            future.result()
        except Exception as exc:
            raise RuntimeError(
                f"Route {route_suffix} failed while post-processing {segment.raw_segment_dir_name}."
            ) from exc


def _prepare_route_recorders(
    video_base: str,
    config_id: str,
    segments: Sequence[RouteSegment],
    serial: str,
    record_start_settle_sec: float,
    on_segment_completed: Callable[[RouteSegment], None] | None = None,
):
    recorder: Recorder | None = None

    def on_record_start(segment_index: int) -> None:
        nonlocal recorder
        if segment_index >= len(segments):
            raise ValueError("record_start count does not match precomputed route segments.")
        segment = segments[segment_index]
        video_path = raw_segment_video_path(video_base, config_id, segment)
        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        if recorder is not None:
            recorder.stop()
        recorder = Recorder(video_path, serial=serial)
        recorder.start()
        time.sleep(record_start_settle_sec)

    def on_record_stop(segment_index: int) -> None:
        nonlocal recorder
        if recorder is not None:
            recorder.stop()
            recorder = None
        if on_segment_completed is not None:
            if segment_index >= len(segments):
                raise ValueError("record_stop count does not match precomputed route segments.")
            on_segment_completed(segments[segment_index])

    def stop_any() -> None:
        nonlocal recorder
        if recorder is not None:
            recorder.stop()
            recorder = None

    return on_record_start, on_record_stop, stop_any


def run_multiroute_workflow(
    runtime_device_context: Mapping[str, object],
    route_subpath: str | None = None,
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
    video_postprocess_mode: str = DEFAULT_VIDEO_POSTPROCESS_MODE,
    video_postprocess_workers: int = DEFAULT_VIDEO_POSTPROCESS_WORKERS,
    video_shortfall_tolerance_sec: float = DEFAULT_SHORTFALL_TOLERANCE_SEC,
) -> None:
    route_root_path = resolve_route_root(route_subpath)
    resolved_postprocess_mode = resolve_video_postprocess_mode(video_postprocess_mode)
    if video_postprocess_workers <= 0:
        raise ValueError("video_postprocess_workers must be >= 1.")
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
    if enable_recording:
        print(f"[INFO] Video postprocess: {resolved_postprocess_mode}")
        print(f"[INFO] Video shortfall tolerance: {video_shortfall_tolerance_sec:.3f}s")
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
        config_id_list = [config_id for _, config_id in configs]
        route_stats = build_split_plan_stats(segments)
        transitioned_in_last_run = False

        print(f"\n[ROUTE] Start route {route_suffix}")
        print(f"[ROUTE] Current portal: {current_portal}")
        if next_portal is not None:
            print(f"[ROUTE] Next portal: {next_portal}")
        print(f"[ROUTE] Segment count: {len(segments)}")
        if segments:
            print(
                "[ROUTE] Split plan: "
                f"original={route_stats.original_segment_count} "
                f"final={route_stats.final_segment_count} "
                f"tail_drops={route_stats.dropped_tail_segment_count} "
                f"tail_drop_total={route_stats.dropped_tail_total_sec:.3f}s "
                f"short_keeps={route_stats.unchanged_short_segment_count}"
            )
        if not enable_recording and segments:
            print(f"[ROUTE] Recording disabled; {len(segments)} record segments will be skipped.")

        if enable_recording:
            cleanup_route_outputs(defaults["video_base"], segments)
        if enable_recording and segments:
            print(f"[ROUTE] Cleared raw and final outputs for route {route_suffix}.")

        postprocess_executor: ThreadPoolExecutor | None = None
        postprocess_jobs: List[Tuple[RouteSegment, Future]] = []
        if enable_recording and segments:
            postprocess_executor = ThreadPoolExecutor(
                max_workers=video_postprocess_workers,
                thread_name_prefix=f"route{route_suffix}_post",
            )

        try:
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
                    on_segment_completed: Callable[[RouteSegment], None] | None = None
                    if config_index == len(configs) and postprocess_executor is not None:
                        def on_segment_completed(
                            segment: RouteSegment,
                            executor: ThreadPoolExecutor = postprocess_executor,
                            config_ids_for_dir: Sequence[str] = tuple(config_id_list),
                        ) -> None:
                            print(
                                f"[POSTPROCESS][QUEUE][{segment.raw_segment_dir_name}] "
                                f"mode={resolved_postprocess_mode}"
                            )
                            future = executor.submit(
                                process_segment_directory,
                                video_base_dir=defaults["video_base"],
                                segment=segment,
                                expected_config_ids=config_ids_for_dir,
                                dry_run=resolved_postprocess_mode == "dry-run",
                                shortfall_tolerance_sec=video_shortfall_tolerance_sec,
                            )
                            postprocess_jobs.append((segment, future))

                    on_record_start, on_record_stop, stop_any = _prepare_route_recorders(
                        video_base=defaults["video_base"],
                        config_id=config_id,
                        segments=segments,
                        serial=str(runtime_device_context["serial"]),
                        record_start_settle_sec=record_start_settle_sec,
                        on_segment_completed=on_segment_completed,
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
        finally:
            if postprocess_executor is not None:
                postprocess_executor.shutdown(wait=True)

        if postprocess_jobs:
            _wait_for_postprocess_jobs(route_suffix, postprocess_jobs)

        if enable_recording:
            if resolved_postprocess_mode == "apply":
                missing = validate_expected_videos(config_id_list, defaults["video_base"], segments)
                if missing:
                    preview = ", ".join(missing[:3])
                    print(
                        f"[WARN] Route {route_suffix} completed but missing {len(missing)} expected videos. "
                        f"Examples: {preview}"
                    )
                else:
                    print(f"[ROUTE] Finished route {route_suffix} ({len(configs)}/{len(configs)})")
            else:
                print(
                    f"[ROUTE] Finished route {route_suffix} dry-run "
                    f"({len(configs)}/{len(configs)})"
                )
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
    route_subpath: str | None = None,
    route_suffixes: Sequence[int] | None = None,
    skip_route_suffixes: Sequence[int] | None = None,
    start_from_route: int | None = None,
    end_at_route: int | None = None,
    step_delay: float = DEFAULT_STEP_DELAY,
    route_gap: float = DEFAULT_ROUTE_GAP,
) -> None:
    route_root_path = resolve_route_root(route_subpath)
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
    route_subpath: str | None = None,
    skip_teleport: bool = False,
    step_delay: float = DEFAULT_STEP_DELAY,
) -> None:
    route_root_path = resolve_route_root(route_subpath)
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
