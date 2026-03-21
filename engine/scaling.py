from __future__ import annotations

import re
from typing import Iterable, Tuple

Resolution = Tuple[int, int]

BASELINE_DEVICE_ID = "huawei_pura70_2848x1276"
BASELINE_DEVICE_LABEL = "HUAWEI Pura 70"
BASELINE_RESOLUTION: Resolution = (2848, 1276)


def normalize_landscape_resolution(width: int, height: int) -> Resolution:
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        raise ValueError(f"Resolution must be positive, got {width}x{height}")
    return max(width, height), min(width, height)


def parse_resolution(value: str | Iterable[int]) -> Resolution:
    if isinstance(value, str):
        match = re.search(r"(\d+)\s*[xX]\s*(\d+)", value.strip())
        if match is None:
            raise ValueError(f"Invalid resolution value: {value!r}")
        return normalize_landscape_resolution(int(match.group(1)), int(match.group(2)))

    values = list(value)
    if len(values) != 2:
        raise ValueError(f"Resolution requires exactly 2 values, got {values!r}")
    return normalize_landscape_resolution(int(values[0]), int(values[1]))


def scale_xy(
    x: int,
    y: int,
    src_resolution: Resolution = BASELINE_RESOLUTION,
    dst_resolution: Resolution = BASELINE_RESOLUTION,
) -> Resolution:
    src_w, src_h = src_resolution
    dst_w, dst_h = dst_resolution
    return round(int(x) * dst_w / src_w), round(int(y) * dst_h / src_h)


def scale_point(
    point: Tuple[int, int],
    dst_resolution: Resolution,
    src_resolution: Resolution = BASELINE_RESOLUTION,
) -> Resolution:
    return scale_xy(point[0], point[1], src_resolution=src_resolution, dst_resolution=dst_resolution)


def format_resolution(resolution: Resolution) -> str:
    return f"{int(resolution[0])}x{int(resolution[1])}"
