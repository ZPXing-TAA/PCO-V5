from __future__ import annotations

from engine.device_context import build_runtime_device_context
from engine.shared_runner import DEFAULT_ROUTE_GAP, DEFAULT_STEP_DELAY, run_debug_multiroute_workflow

# Shared local control surface.
# Device-bound values are auto-discovered at runtime.
ROUTE_SUBPATH = "mondstadt"  # "natlan" | "mondstadt"
SKIP_ROUTE_SUFFIXES = []
START_FROM_ROUTE = 11
END_AT_ROUTE = 15

STEP_DELAY = DEFAULT_STEP_DELAY
ROUTE_GAP = DEFAULT_ROUTE_GAP


def main() -> None:
    runtime_device_context = build_runtime_device_context()
    run_debug_multiroute_workflow(
        runtime_device_context=runtime_device_context,
        route_subpath=ROUTE_SUBPATH,
        skip_route_suffixes=SKIP_ROUTE_SUFFIXES,
        start_from_route=START_FROM_ROUTE,
        end_at_route=END_AT_ROUTE,
        step_delay=STEP_DELAY,
        route_gap=ROUTE_GAP,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[INTERRUPT] Ctrl+C received.")
