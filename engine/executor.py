from __future__ import annotations

import time
from typing import Any, Dict

from engine.adb import shell_input_swipe, shell_input_tap


def exec_action(step: Dict[str, Any], serial: str) -> None:
    action_type = step["type"]
    if action_type == "tap":
        shell_input_tap(step["x"], step["y"], serial=serial)
        return
    if action_type == "swipe":
        x1, y1 = step["start"]
        x2, y2 = step["end"]
        shell_input_swipe(x1, y1, x2, y2, step["duration"], serial=serial)
        return
    if action_type == "sleep":
        time.sleep(step["time"])
        return
    if action_type == "info":
        print(f"[INFO] {step.get('message', '')}")
        return
    raise ValueError(f"Unknown action type: {action_type}")
