from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any, Dict, Mapping

from engine.executor import exec_action
from engine.scaling import BASELINE_RESOLUTION, scale_xy


def _map_step(step: Dict[str, Any], target_resolution: tuple[int, int]) -> Dict[str, Any]:
    mapped = deepcopy(step)
    action_type = mapped.get("type")
    if action_type == "tap":
        mapped["x"], mapped["y"] = scale_xy(
            mapped["x"],
            mapped["y"],
            src_resolution=BASELINE_RESOLUTION,
            dst_resolution=target_resolution,
        )
    elif action_type == "swipe":
        x1, y1 = mapped["start"]
        x2, y2 = mapped["end"]
        mapped["start"] = list(
            scale_xy(x1, y1, src_resolution=BASELINE_RESOLUTION, dst_resolution=target_resolution)
        )
        mapped["end"] = list(
            scale_xy(x2, y2, src_resolution=BASELINE_RESOLUTION, dst_resolution=target_resolution)
        )
    return mapped


def apply_render_config(json_path: str, runtime_device_context: Mapping[str, object]) -> None:
    with open(json_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    target_resolution = tuple(runtime_device_context["target_resolution"])
    serial = str(runtime_device_context["serial"])
    for step in data["steps"]:
        exec_action(_map_step(step, target_resolution), serial=serial)
    time.sleep(1)
