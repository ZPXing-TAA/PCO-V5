import os
import shutil
from collections import defaultdict
from dataclasses import dataclass
from math import floor
from typing import Iterable, List, Sequence, Tuple


PLANNED_CLIP_LENGTH_SEC = 5.0
RAW_SEGMENTS_DIRNAME = "_raw_segments"


@dataclass(frozen=True)
class FinalSegment:
    parent_segment_index: int
    clip_index_within_parent: int
    raw_action_name: str
    label_name: str
    occurrence_index_within_label: int
    segment_dir_name: str


@dataclass(frozen=True)
class RouteSegment:
    segment_index: int
    raw_action_name: str
    label_name: str
    occurrence_index_within_label: int
    raw_segment_dir_name: str
    route_duration_sec: float
    planned_clip_count: int
    planned_tail_drop_sec: float
    planned_final_segments: Tuple[FinalSegment, ...]

    @property
    def planned_end_sec(self) -> float:
        if self.route_duration_sec < PLANNED_CLIP_LENGTH_SEC:
            return self.route_duration_sec
        return self.planned_clip_count * PLANNED_CLIP_LENGTH_SEC


@dataclass(frozen=True)
class SplitPlanStats:
    original_segment_count: int
    final_segment_count: int
    dropped_tail_segment_count: int
    dropped_tail_total_sec: float
    unchanged_short_segment_count: int

def build_route_segments(route: Sequence[Sequence[object]], country: str, route_suffix: int) -> List[RouteSegment]:
    segments: List[RouteSegment] = []
    raw_label_occurrences = defaultdict(int)
    final_label_occurrences = defaultdict(int)
    recorded_step: Sequence[object] | None = None
    inside_record_window = False

    for index, step in enumerate(route):
        name = step[0]
        if name == "record_start":
            if inside_record_window:
                raise ValueError(f"Nested record_start found near route step {index}.")
            inside_record_window = True
            recorded_step = None
            continue

        if name == "record_stop":
            if not inside_record_window:
                raise ValueError(f"record_stop without record_start found near route step {index}.")
            if recorded_step is None:
                raise ValueError(f"Empty record window found near route step {index}.")

            action_name = str(recorded_step[0])
            route_duration_sec = _route_duration_sec(recorded_step, route_index=index)
            segment_index = len(segments) + 1
            raw_label_occurrences[action_name] += 1
            occurrence_index = raw_label_occurrences[action_name]
            planned_clip_count = _planned_clip_count(route_duration_sec)
            planned_final_segments = []
            for clip_index in range(planned_clip_count):
                final_label_occurrences[action_name] += 1
                final_occurrence_index = final_label_occurrences[action_name]
                planned_final_segments.append(
                    FinalSegment(
                        parent_segment_index=segment_index,
                        clip_index_within_parent=clip_index + 1,
                        raw_action_name=action_name,
                        label_name=action_name,
                        occurrence_index_within_label=final_occurrence_index,
                        segment_dir_name=(
                            f"{country}_r{route_suffix:02d}_{action_name}{final_occurrence_index:02d}"
                        ),
                    )
                )

            planned_tail_drop_sec = max(0.0, route_duration_sec - (planned_clip_count * PLANNED_CLIP_LENGTH_SEC))
            segments.append(
                RouteSegment(
                    segment_index=segment_index,
                    raw_action_name=action_name,
                    label_name=action_name,
                    occurrence_index_within_label=occurrence_index,
                    raw_segment_dir_name=f"{country}_r{route_suffix:02d}_{action_name}{occurrence_index:02d}",
                    route_duration_sec=route_duration_sec,
                    planned_clip_count=planned_clip_count,
                    planned_tail_drop_sec=planned_tail_drop_sec,
                    planned_final_segments=tuple(planned_final_segments),
                )
            )
            inside_record_window = False
            recorded_step = None
            continue

        if inside_record_window:
            if recorded_step is not None:
                raise ValueError(
                    f"Record window near route step {index} contains more than one action: "
                    f"{recorded_step!r} and {step!r}"
                )
            recorded_step = step

    if inside_record_window:
        raise ValueError("Route ended before record_stop.")
    return segments


def _route_duration_sec(step: Sequence[object], route_index: int) -> float:
    if len(step) < 2 or not isinstance(step[1], (int, float)):
        raise ValueError(
            f"Recorded action at route step {route_index} must provide a numeric duration. Got {step!r}."
        )
    duration = float(step[1])
    if duration <= 0:
        raise ValueError(f"Recorded action duration must be > 0. Got {step!r}.")
    return duration


def _planned_clip_count(route_duration_sec: float) -> int:
    if route_duration_sec < PLANNED_CLIP_LENGTH_SEC:
        return 1
    planned = floor((route_duration_sec / PLANNED_CLIP_LENGTH_SEC) + 1e-9)
    return max(1, planned)


def raw_segment_output_dir(video_base_dir: str, segment: RouteSegment) -> str:
    return os.path.join(video_base_dir, RAW_SEGMENTS_DIRNAME, segment.label_name, segment.raw_segment_dir_name)


def raw_segment_video_path(video_base_dir: str, config_id: str, segment: RouteSegment) -> str:
    return os.path.join(raw_segment_output_dir(video_base_dir, segment), f"{config_id}.mp4")


def final_segment_output_dir(video_base_dir: str, final_segment: FinalSegment) -> str:
    return os.path.join(video_base_dir, final_segment.label_name, final_segment.segment_dir_name)


def final_segment_video_path(video_base_dir: str, config_id: str, final_segment: FinalSegment) -> str:
    return os.path.join(final_segment_output_dir(video_base_dir, final_segment), f"{config_id}.mp4")


def iter_final_segments(segments: Iterable[RouteSegment]) -> List[FinalSegment]:
    final_segments: List[FinalSegment] = []
    for segment in segments:
        final_segments.extend(segment.planned_final_segments)
    return final_segments


def planned_video_paths(video_base_dir: str, config_id: str, segments: Iterable[RouteSegment]) -> List[str]:
    return [final_segment_video_path(video_base_dir, config_id, segment) for segment in iter_final_segments(segments)]


def validate_expected_videos(
    config_ids: Iterable[str],
    video_base_dir: str,
    segments: Iterable[RouteSegment],
) -> List[str]:
    missing: List[str] = []
    final_segment_list = iter_final_segments(segments)
    for config_id in config_ids:
        for path in [final_segment_video_path(video_base_dir, config_id, segment) for segment in final_segment_list]:
            if not os.path.exists(path):
                missing.append(path)
    return missing


def cleanup_route_outputs(video_base_dir: str, segments: Iterable[RouteSegment]) -> None:
    seen = set()
    for segment in segments:
        path = raw_segment_output_dir(video_base_dir, segment)
        if path not in seen:
            seen.add(path)
            if os.path.isdir(path):
                shutil.rmtree(path)
        for final_segment in segment.planned_final_segments:
            path = final_segment_output_dir(video_base_dir, final_segment)
            if path in seen:
                continue
            seen.add(path)
            if os.path.isdir(path):
                shutil.rmtree(path)


def build_split_plan_stats(segments: Iterable[RouteSegment]) -> SplitPlanStats:
    segment_list = list(segments)
    return SplitPlanStats(
        original_segment_count=len(segment_list),
        final_segment_count=sum(segment.planned_clip_count for segment in segment_list),
        dropped_tail_segment_count=sum(1 for segment in segment_list if segment.planned_tail_drop_sec > 1e-9),
        dropped_tail_total_sec=sum(segment.planned_tail_drop_sec for segment in segment_list),
        unchanged_short_segment_count=sum(
            1 for segment in segment_list if segment.route_duration_sec < PLANNED_CLIP_LENGTH_SEC
        ),
    )
