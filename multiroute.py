from __future__ import annotations

from engine.device_context import build_runtime_device_context
from engine.shared_runner import (
    DEFAULT_RECORD_START_SETTLE_SEC,
    DEFAULT_ROUTE_GAP,
    DEFAULT_STEP_DELAY,
    DEFAULT_VIDEO_POSTPROCESS_MODE,
    DEFAULT_VIDEO_POSTPROCESS_WORKERS,
    run_multiroute_workflow,
)
from engine.video_postprocess import DEFAULT_SHORTFALL_TOLERANCE_SEC

# Shared local control surface.
# Device-bound values are auto-discovered at runtime.
ROUTE_SUBPATH = "natlan"  # "natlan" | "mondstadt"
SKIP_ROUTE_SUFFIXES = []
START_FROM_ROUTE = 1
END_AT_ROUTE = 30

TOTAL_CONFIGS_PER_ROUTE = 80
STEP_DELAY = DEFAULT_STEP_DELAY
ROUTE_GAP = DEFAULT_ROUTE_GAP
RECORD_START_SETTLE_SEC = DEFAULT_RECORD_START_SETTLE_SEC
VIDEO_POSTPROCESS_MODE = DEFAULT_VIDEO_POSTPROCESS_MODE  # "apply" | "dry-run"
VIDEO_POSTPROCESS_WORKERS = DEFAULT_VIDEO_POSTPROCESS_WORKERS
VIDEO_SHORTFALL_TOLERANCE_SEC = DEFAULT_SHORTFALL_TOLERANCE_SEC


def main() -> None:
    runtime_device_context = build_runtime_device_context(total_configs_per_route=TOTAL_CONFIGS_PER_ROUTE)
    run_multiroute_workflow(
        runtime_device_context=runtime_device_context,
        route_subpath=ROUTE_SUBPATH,
        skip_route_suffixes=SKIP_ROUTE_SUFFIXES,
        start_from_route=START_FROM_ROUTE,
        end_at_route=END_AT_ROUTE,
        step_delay=STEP_DELAY,
        route_gap=ROUTE_GAP,
        record_start_settle_sec=RECORD_START_SETTLE_SEC,
        video_postprocess_mode=VIDEO_POSTPROCESS_MODE,
        video_postprocess_workers=VIDEO_POSTPROCESS_WORKERS,
        video_shortfall_tolerance_sec=VIDEO_SHORTFALL_TOLERANCE_SEC,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[INTERRUPT] Ctrl+C received, exit.")
