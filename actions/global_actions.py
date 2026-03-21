from __future__ import annotations

import os
import time
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

from engine.adb import shell_input_swipe, shell_input_tap
from engine.scaling import BASELINE_RESOLUTION, scale_point

OffsetMap = Mapping[str, Tuple[int, int]]
PointMap = Dict[str, Tuple[int, int]]

BASE_POINTS: PointMap = {
    "MOVE_START": (523, 800),
    "MOVE_END": (523, 700),
    "ATTACK": (2280, 980),
    "JUMP": (2510, 830),
    "SPRINT": (2500, 1125),
    "UTIL": (2060, 1120),
    "FIG1": (0, 0),
    "FIG2": (0, 0),
    "FIG3": (0, 0),
    "TURN_180_L": (550, 300),
    "TURN_180_R": (1766, 300),
    "TURN_90_R_L": (550, 300),
    "TURN_90_R_R": (1158, 300),
    "TURN_90_L_L": (1158, 300),
    "TURN_90_L_R": (500, 300),
    "TURN_45_R_L": (550, 300),
    "TURN_45_R_R": (854, 300),
    "TURN_45_L_L": (854, 300),
    "TURN_45_L_R": (550, 300),
    "TURN_30_R_L": (550, 300),
    "TURN_30_R_R": (753, 300),
    "TURN_30_L_L": (753, 300),
    "TURN_30_L_R": (550, 300),
    "TURN_135_R_L": (550, 300),
    "TURN_135_R_R": (1462, 300),
    "TURN_135_L_L": (1462, 300),
    "TURN_135_L_R": (550, 300),
    "OPEN_MAP": (400, 200),
    "CONFIRM_TELEPORT": (2450, 1180),
    "ADJUST_GAME_TIME_P1": (175, 60),
    "ADJUST_GAME_TIME_P2": (165, 870),
    "ADJUST_GAME_TIME_S1": (2125, 515),
    "ADJUST_GAME_TIME_S2": (2125, 615),
    "ADJUST_GAME_TIME_S3": (2005, 615),
    "ADJUST_GAME_TIME_S4": (2005, 515),
    "ADJUST_GAME_TIME_S5": (2125, 515),
    "ADJUST_GAME_TIME_P3": (2080, 1200),
    "ADJUST_GAME_TIME_P4": (2654, 62),
    "ADJUST_GAME_TIME_P5": (165, 90),
}

POINT_GROUPS: Dict[str, Tuple[str, ...]] = {
    "MOVE_START": ("MOVE",),
    "MOVE_END": ("MOVE",),
    "ATTACK": ("ATTACK",),
    "JUMP": ("JUMP",),
    "SPRINT": ("SPRINT",),
    "UTIL": ("UTIL",),
    "FIG1": ("FIG",),
    "FIG2": ("FIG",),
    "FIG3": ("FIG",),
    "TURN_180_L": ("TURN", "TURN_180"),
    "TURN_180_R": ("TURN", "TURN_180"),
    "TURN_90_R_L": ("TURN", "TURN_90_R"),
    "TURN_90_R_R": ("TURN", "TURN_90_R"),
    "TURN_90_L_L": ("TURN", "TURN_90_L"),
    "TURN_90_L_R": ("TURN", "TURN_90_L"),
    "TURN_45_R_L": ("TURN", "TURN_45_R"),
    "TURN_45_R_R": ("TURN", "TURN_45_R"),
    "TURN_45_L_L": ("TURN", "TURN_45_L"),
    "TURN_45_L_R": ("TURN", "TURN_45_L"),
    "TURN_30_R_L": ("TURN", "TURN_30_R"),
    "TURN_30_R_R": ("TURN", "TURN_30_R"),
    "TURN_30_L_L": ("TURN", "TURN_30_L"),
    "TURN_30_L_R": ("TURN", "TURN_30_L"),
    "TURN_135_R_L": ("TURN", "TURN_135_R"),
    "TURN_135_R_R": ("TURN", "TURN_135_R"),
    "TURN_135_L_L": ("TURN", "TURN_135_L"),
    "TURN_135_L_R": ("TURN", "TURN_135_L"),
    "OPEN_MAP": ("OPEN_MAP",),
    "CONFIRM_TELEPORT": ("CONFIRM_TELEPORT",),
    "ADJUST_GAME_TIME_P1": ("ADJUST_GAME_TIME",),
    "ADJUST_GAME_TIME_P2": ("ADJUST_GAME_TIME",),
    "ADJUST_GAME_TIME_S1": ("ADJUST_GAME_TIME",),
    "ADJUST_GAME_TIME_S2": ("ADJUST_GAME_TIME",),
    "ADJUST_GAME_TIME_S3": ("ADJUST_GAME_TIME",),
    "ADJUST_GAME_TIME_S4": ("ADJUST_GAME_TIME",),
    "ADJUST_GAME_TIME_S5": ("ADJUST_GAME_TIME",),
    "ADJUST_GAME_TIME_P3": ("ADJUST_GAME_TIME",),
    "ADJUST_GAME_TIME_P4": ("ADJUST_GAME_TIME",),
}


def _add(point: Tuple[int, int], offset: Tuple[int, int]) -> Tuple[int, int]:
    return point[0] + offset[0], point[1] + offset[1]


def _env_offset(key: str) -> Tuple[int, int]:
    return int(os.environ.get(f"{key}_X_OFFSET", "0")), int(os.environ.get(f"{key}_Y_OFFSET", "0"))


def _resolve_point(
    name: str,
    scaled_point: Tuple[int, int],
    offsets: OffsetMap,
    use_env_offsets: bool,
) -> Tuple[int, int]:
    point = scaled_point
    keys: Iterable[str] = ("GLOBAL",) + POINT_GROUPS.get(name, ()) + (name,)
    for key in keys:
        if key in offsets:
            point = _add(point, tuple(offsets[key]))
        if use_env_offsets:
            point = _add(point, _env_offset(key))
    return int(point[0]), int(point[1])


def build_actions(
    runtime_device_context: Mapping[str, object],
    use_env_offsets: bool = True,
) -> Dict[str, object]:
    target_resolution = tuple(runtime_device_context["target_resolution"])
    serial = str(runtime_device_context["serial"])
    offsets = runtime_device_context.get("offsets", {}) or {}

    mapped_points: PointMap = {
        name: scale_point(point, dst_resolution=target_resolution, src_resolution=BASELINE_RESOLUTION)
        for name, point in BASE_POINTS.items()
    }
    points: PointMap = {
        name: _resolve_point(name, mapped_point, offsets, use_env_offsets=use_env_offsets)
        for name, mapped_point in mapped_points.items()
    }

    glide_hold_ms = int(os.environ.get("AUTO_GLIDE_UTIL_HOLD_MS", "1400"))
    glide_after_util_delay = float(os.environ.get("AUTO_GLIDE_AFTER_UTIL_DELAY_SEC", "0.7"))

    def tap(x: int, y: int) -> None:
        shell_input_tap(x, y, serial=serial)

    def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> None:
        shell_input_swipe(x1, y1, x2, y2, duration_ms, serial=serial)

    def move(seconds: float) -> None:
        swipe(*points["MOVE_START"], *points["MOVE_END"], int(seconds * 1000))

    def walk(seconds: float) -> None:
        move(seconds)

    def climb(seconds: float) -> None:
        move(seconds)

    def swim(seconds: float) -> None:
        move(seconds)

    def attack() -> None:
        tap(*points["ATTACK"])

    def heavy_attack() -> None:
        x, y = points["ATTACK"]
        swipe(x, y, x, y, 1000)

    def long_attack(seconds: float) -> None:
        x, y = points["ATTACK"]
        swipe(x, y, x, y, int(seconds * 1000))

    def jump() -> None:
        tap(*points["JUMP"])

    def dash() -> None:
        tap(*points["SPRINT"])

    def run(seconds: float) -> None:
        tap(*points["SPRINT"])
        sleep(0.1)
        move(seconds)

    def util() -> None:
        tap(*points["UTIL"])

    def long_util(seconds: float = 1.0) -> None:
        x, y = points["UTIL"]
        swipe(x, y, x, y, int(seconds * 1000))

    def fig1() -> None:
        tap(*points["FIG1"])

    def fig2() -> None:
        tap(*points["FIG2"])

    def fig3() -> None:
        tap(*points["FIG3"])

    def combat() -> None:
        fig2()
        time.sleep(0.5)
        long_util()
        time.sleep(1)
        fig3()
        time.sleep(1)
        util()
        time.sleep(1)
        fig1()
        time.sleep(1)
        util()
        time.sleep(1)
        long_attack(5)
        fig2()
        time.sleep(1)

    def glide(seconds: float) -> None:
        long_util(glide_hold_ms / 1000.0)
        time.sleep(glide_after_util_delay)
        tap(*points["JUMP"])
        move(seconds)

    def sleep(seconds: float) -> None:
        time.sleep(seconds)

    def turn_180() -> None:
        swipe(*points["TURN_180_L"], *points["TURN_180_R"], 800)

    def turn_right_90() -> None:
        swipe(*points["TURN_90_R_L"], *points["TURN_90_R_R"], 600)

    def turn_left_90() -> None:
        swipe(*points["TURN_90_L_L"], *points["TURN_90_L_R"], 600)

    def turn_right_45() -> None:
        swipe(*points["TURN_45_R_L"], *points["TURN_45_R_R"], 600)

    def turn_left_45() -> None:
        swipe(*points["TURN_45_L_L"], *points["TURN_45_L_R"], 600)

    def turn_right_30() -> None:
        swipe(*points["TURN_30_R_L"], *points["TURN_30_R_R"], 600)

    def turn_left_30() -> None:
        swipe(*points["TURN_30_L_L"], *points["TURN_30_L_R"], 600)

    def turn_right_135() -> None:
        swipe(*points["TURN_135_R_L"], *points["TURN_135_R_R"], 700)

    def turn_left_135() -> None:
        swipe(*points["TURN_135_L_L"], *points["TURN_135_L_R"], 700)

    def open_map() -> None:
        tap(*points["OPEN_MAP"])

    def confirm_teleport() -> None:
        tap(*points["CONFIRM_TELEPORT"])
        time.sleep(5.0)

    def adjust_game_time() -> None:
        tap(*points["ADJUST_GAME_TIME_P1"])
        time.sleep(1)
        tap(*points["ADJUST_GAME_TIME_P2"])
        time.sleep(1)
        swipe(*points["ADJUST_GAME_TIME_S1"], *points["ADJUST_GAME_TIME_S2"], 300)
        time.sleep(0.2)
        swipe(*points["ADJUST_GAME_TIME_S2"], *points["ADJUST_GAME_TIME_S3"], 300)
        time.sleep(0.2)
        swipe(*points["ADJUST_GAME_TIME_S3"], *points["ADJUST_GAME_TIME_S4"], 300)
        time.sleep(0.2)
        swipe(*points["ADJUST_GAME_TIME_S4"], *points["ADJUST_GAME_TIME_S5"], 300)
        time.sleep(0.3)
        tap(*points["ADJUST_GAME_TIME_P3"])
        time.sleep(20)
        tap(*points["ADJUST_GAME_TIME_P4"])
        time.sleep(1)
        tap(*points["ADJUST_GAME_TIME_P5"])
        time.sleep(5)

    return {
        "tap": tap,
        "swipe": swipe,
        "move": move,
        "walk": walk,
        "climb": climb,
        "swim": swim,
        "attack": attack,
        "heavy_attack": heavy_attack,
        "long_attack": long_attack,
        "jump": jump,
        "dash": dash,
        "run": run,
        "util": util,
        "long_util": long_util,
        "fig1": fig1,
        "fig2": fig2,
        "fig3": fig3,
        "combat": combat,
        "glide": glide,
        "sleep": sleep,
        "turn_180": turn_180,
        "turn_right_90": turn_right_90,
        "turn_left_90": turn_left_90,
        "turn_right_45": turn_right_45,
        "turn_left_45": turn_left_45,
        "turn_right_30": turn_right_30,
        "turn_left_30": turn_left_30,
        "turn_right_135": turn_right_135,
        "turn_left_135": turn_left_135,
        "open_map": open_map,
        "confirm_teleport": confirm_teleport,
        "adjust_game_time": adjust_game_time,
        "POINTS": points,
        "BASE_RESOLUTION": BASELINE_RESOLUTION,
        "TARGET_RESOLUTION": target_resolution,
        "SERIAL": serial,
    }


def bind_actions(
    namespace: MutableMapping[str, object],
    runtime_device_context: Mapping[str, object],
    use_env_offsets: bool = True,
) -> None:
    namespace.update(build_actions(runtime_device_context, use_env_offsets=use_env_offsets))
