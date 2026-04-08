from __future__ import annotations

from engine.device_context import build_runtime_device_context
from engine.shared_runner import (
    DEFAULT_RECORD_START_SETTLE_SEC,
    DEFAULT_STEP_DELAY,
    DEFAULT_VIDEO_POSTPROCESS_MODE,
    DEFAULT_VIDEO_POSTPROCESS_WORKERS,
    run_multiroute_workflow,
)
from engine.video_postprocess import DEFAULT_SHORTFALL_TOLERANCE_SEC

# Shared local control surface for partial re-recording on one route.
# Device-bound values are auto-discovered at runtime.
ROUTE_SUBPATH = "mondstadt"  # "natlan" | "mondstadt" | "fontaine"
ROUTE_SUFFIX = 7

START_FROM_CONFIG_INDEX = 52  # 1-based, inclusive
END_AT_CONFIG_INDEX = None  # 1-based, inclusive; None means run through the last config

TOTAL_CONFIGS_PER_ROUTE = 80
STEP_DELAY = DEFAULT_STEP_DELAY
RECORD_START_SETTLE_SEC = DEFAULT_RECORD_START_SETTLE_SEC
VIDEO_POSTPROCESS_MODE = DEFAULT_VIDEO_POSTPROCESS_MODE  # "apply" | "dry-run"
VIDEO_POSTPROCESS_WORKERS = DEFAULT_VIDEO_POSTPROCESS_WORKERS
VIDEO_SHORTFALL_TOLERANCE_SEC = DEFAULT_SHORTFALL_TOLERANCE_SEC
USE_NEXT_PORTAL_ON_LAST_CONFIG = False


def main() -> None:
    if ROUTE_SUFFIX <= 0:
        raise ValueError("ROUTE_SUFFIX must be a positive integer.")
    if START_FROM_CONFIG_INDEX <= 0:
        raise ValueError("START_FROM_CONFIG_INDEX must be >= 1.")
    if END_AT_CONFIG_INDEX is not None and END_AT_CONFIG_INDEX <= 0:
        raise ValueError("END_AT_CONFIG_INDEX must be >= 1 when provided.")
    if END_AT_CONFIG_INDEX is not None and START_FROM_CONFIG_INDEX > END_AT_CONFIG_INDEX:
        raise ValueError("START_FROM_CONFIG_INDEX must be <= END_AT_CONFIG_INDEX.")

    runtime_device_context = build_runtime_device_context(total_configs_per_route=TOTAL_CONFIGS_PER_ROUTE)
    run_multiroute_workflow(
        runtime_device_context=runtime_device_context,
        route_subpath=ROUTE_SUBPATH,
        route_suffixes=[ROUTE_SUFFIX],
        start_from_config_index=START_FROM_CONFIG_INDEX,
        end_at_config_index=END_AT_CONFIG_INDEX,
        step_delay=STEP_DELAY,
        record_start_settle_sec=RECORD_START_SETTLE_SEC,
        use_next_portal_on_last_config=USE_NEXT_PORTAL_ON_LAST_CONFIG,
        video_postprocess_mode=VIDEO_POSTPROCESS_MODE,
        video_postprocess_workers=VIDEO_POSTPROCESS_WORKERS,
        video_shortfall_tolerance_sec=VIDEO_SHORTFALL_TOLERANCE_SEC,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[INTERRUPT] Ctrl+C received, exit.")
