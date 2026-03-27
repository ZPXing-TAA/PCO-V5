from __future__ import annotations

from engine.device_context import build_runtime_device_context
from engine.shared_runner import DEFAULT_STEP_DELAY, run_multiroute_workflow

# Fixed measurement order from /Users/xingzhengpeng/Downloads/measure_12_key_configs.md
ROUTE_SUBPATH = "natlan"  # "natlan" | "mondstadt"
ROUTE_SUFFIX = 1
STEP_DELAY = DEFAULT_STEP_DELAY

MEASUREMENT_CONFIG_IDS = [
    "Medium_30_Low_Low",
    "High_60_Low_Low",
    "Lowest_30_Low_Low",
    "Medium_30_High_Low",
    "Medium_30_Low_Low",
    "VeryHigh_30_Low_Low",
    "Medium_30_Low_High",
    "Medium_24_Low_Low",
    "Medium_30_Low_Low",
    "VeryHigh_60_Low_Low",
    "Medium_45_Low_Low",
    "VeryHigh_60_High_High",
]


def main() -> None:
    runtime_device_context = build_runtime_device_context()
    run_multiroute_workflow(
        runtime_device_context=runtime_device_context,
        route_subpath=ROUTE_SUBPATH,
        route_suffixes=[ROUTE_SUFFIX],
        config_ids=MEASUREMENT_CONFIG_IDS,
        step_delay=STEP_DELAY,
        enable_recording=False,
        use_next_portal_on_last_config=False,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[INTERRUPT] Ctrl+C received, exit.")
