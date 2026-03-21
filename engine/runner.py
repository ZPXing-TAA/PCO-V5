from __future__ import annotations

import time
from typing import Callable, Mapping, MutableMapping, Sequence

from actions.global_actions import build_actions

ActionTable = MutableMapping[str, Callable[..., None]]


def build_action_table(runtime_device_context: Mapping[str, object]) -> ActionTable:
    actions = build_actions(runtime_device_context=runtime_device_context)

    def teleport(portal: Sequence[int]) -> None:
        actions["open_map"]()
        time.sleep(1.5)
        actions["tap"](*portal)
        time.sleep(1.5)
        actions["confirm_teleport"]()
        time.sleep(3)

    action_table: ActionTable = {
        "move": actions["move"],
        "walk": actions["walk"],
        "climb": actions["climb"],
        "swim": actions["swim"],
        "run": actions["run"],
        "dash": actions["dash"],
        "attack": lambda: actions["attack"](),
        "heavy_attack": lambda: actions["heavy_attack"](),
        "jump": lambda: actions["jump"](),
        "util": lambda: actions["util"](),
        "long_util": lambda: actions["long_util"](),
        "combat": lambda: actions["combat"](),
        "glide": actions["glide"],
        "turn_180": lambda: actions["turn_180"](),
        "turn_right_90": lambda: actions["turn_right_90"](),
        "turn_left_90": lambda: actions["turn_left_90"](),
        "turn_right_45": lambda: actions["turn_right_45"](),
        "turn_left_45": lambda: actions["turn_left_45"](),
        "turn_right_30": lambda: actions["turn_right_30"](),
        "turn_left_30": lambda: actions["turn_left_30"](),
        "turn_right_135": lambda: actions["turn_right_135"](),
        "turn_left_135": lambda: actions["turn_left_135"](),
        "teleport": teleport,
        "sleep": actions["sleep"],
    }
    if "adjust_game_time" in actions:
        action_table["adjust_game_time"] = lambda: actions["adjust_game_time"]()
    return action_table


def run_route(
    route: Sequence[Sequence[object]],
    action_table: Mapping[str, Callable[..., None]],
    step_delay: float,
    current_portal: Sequence[int] | None = None,
    teleport_portal: Sequence[int] | None = None,
    on_record_start: Callable[[int], None] | None = None,
    on_record_stop: Callable[[int], None] | None = None,
    skip_record_actions: bool = False,
    skip_in_route_teleport: bool = False,
) -> dict[str, object]:
    record_index = -1
    teleport_used = False

    for step in route:
        name = step[0]
        args = step[1:] if len(step) > 1 else []
        print(f"[ACTION] {name} {tuple(args)}")

        if name == "record_start":
            record_index += 1
            if skip_record_actions:
                print("[DEBUG] Skip action: record_start")
            elif on_record_start is not None:
                on_record_start(record_index)
            continue

        if name == "record_stop":
            if skip_record_actions:
                print("[DEBUG] Skip action: record_stop")
            elif on_record_stop is not None:
                on_record_stop(record_index)
            continue

        if name == "teleport":
            if skip_in_route_teleport:
                print(f"[DEBUG] Skip in-route teleport {tuple(args)}")
                time.sleep(step_delay)
                continue
            portal = teleport_portal if teleport_portal is not None else current_portal
            if portal is None:
                raise ValueError("Teleport requested but no portal was supplied.")
            action_table["teleport"](portal)
            teleport_used = True
        else:
            action_table[name](*args)

        time.sleep(step_delay)

    return {
        "teleport_used": teleport_used,
        "record_starts_seen": record_index + 1,
    }
