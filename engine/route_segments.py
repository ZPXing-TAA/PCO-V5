import os
import shutil
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class RouteSegment:
    segment_index: int
    raw_action_name: str
    label_name: str
    occurrence_index_within_label: int
    segment_dir_name: str


def _next_recorded_action(route: Sequence[Sequence[object]], start_index: int) -> str:
    for step in route[start_index + 1:]:
        name = step[0]
        if name not in ("record_start", "record_stop"):
            return name
    return "unknown"


def build_route_segments(route: Sequence[Sequence[object]], country: str, route_suffix: int) -> List[RouteSegment]:
    segments: List[RouteSegment] = []
    label_occurrences = defaultdict(int)
    for index, step in enumerate(route):
        if step[0] != "record_start":
            continue
        action_name = _next_recorded_action(route, index)
        segment_index = len(segments) + 1
        label_occurrences[action_name] += 1
        occurrence_index = label_occurrences[action_name]
        segments.append(
            RouteSegment(
                segment_index=segment_index,
                raw_action_name=action_name,
                label_name=action_name,
                occurrence_index_within_label=occurrence_index,
                segment_dir_name=f"{country}_r{route_suffix:02d}_{action_name}{occurrence_index:02d}",
            )
        )
    return segments


def segment_output_dir(video_base_dir: str, segment: RouteSegment) -> str:
    return os.path.join(video_base_dir, segment.label_name, segment.segment_dir_name)


def segment_video_path(video_base_dir: str, config_id: str, segment: RouteSegment) -> str:
    return os.path.join(segment_output_dir(video_base_dir, segment), f"{config_id}.mp4")


def planned_video_paths(video_base_dir: str, config_id: str, segments: Iterable[RouteSegment]) -> List[str]:
    return [segment_video_path(video_base_dir, config_id, segment) for segment in segments]


def validate_expected_videos(
    config_ids: Iterable[str],
    video_base_dir: str,
    segments: Iterable[RouteSegment],
) -> List[str]:
    missing: List[str] = []
    segment_list = list(segments)
    for config_id in config_ids:
        for path in planned_video_paths(video_base_dir, config_id, segment_list):
            if not os.path.exists(path):
                missing.append(path)
    return missing


def cleanup_route_outputs(video_base_dir: str, segments: Iterable[RouteSegment]) -> None:
    seen = set()
    for segment in segments:
        path = segment_output_dir(video_base_dir, segment)
        if path in seen:
            continue
        seen.add(path)
        if os.path.isdir(path):
            shutil.rmtree(path)
