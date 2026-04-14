from __future__ import annotations

from engine.device_context import build_runtime_device_context
from engine.shared_runner import DEFAULT_STEP_DELAY, run_test_route_workflow

# Shared local control surface.
# Device-bound values are auto-discovered at runtime.
ROUTE_SUBPATH = "mondstadt"  # Any existing directory name under routes/
ROUTE_SUFFIX = 24
TEST_MODE = "single"  # "single" | "current_next"
# TEST_MODE = "current_next"  # "single" | "current_next"
SKIP_TELEPORT = True 
# SKIP_TELEPORT = False
STEP_DELAY = DEFAULT_STEP_DELAY


def main() -> None:
    if ROUTE_SUFFIX <= 0:
        raise ValueError("Set ROUTE_SUFFIX to a positive integer before running test_route.py.")
    if TEST_MODE not in {"single", "current_next"}:
        raise ValueError("TEST_MODE must be 'single' or 'current_next'.")

    runtime_device_context = build_runtime_device_context()
    run_test_route_workflow(
        runtime_device_context=runtime_device_context,
        route_subpath=ROUTE_SUBPATH,
        route_suffix=ROUTE_SUFFIX,
        test_mode=TEST_MODE,
        skip_teleport=SKIP_TELEPORT,
        step_delay=STEP_DELAY,
    )


if __name__ == "__main__":
    main()
