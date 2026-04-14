from __future__ import annotations
import os
import shutil
from collections import defaultdict
from dataclasses import dataclass
from math import floor
from typing import Iterable, List, Sequence, Tuple


PLANNED_CLIP_LENGTH_SEC = 5.0
RAW_SEGMENTS_DIRNAME = "_raw_segments"
NON_RECORDABLE_DURATION_ACTIONS = {"record_start", "record_stop", "sleep"}


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

    for index, step in enumerate(route):
        if not should_record_route_step(step):
            continue

        action_name = str(step[0])
        route_duration_sec = _route_duration_sec(step, route_index=index)
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

    return segments


def should_record_route_step(step: Sequence[object]) -> bool:
    if not step:
        return False
    action_name = str(step[0])
    if action_name in NON_RECORDABLE_DURATION_ACTIONS:
        return False
    if len(step) < 2 or not isinstance(step[1], (int, float)):
        return False
    return float(step[1]) >= PLANNED_CLIP_LENGTH_SEC


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


def cleanup_route_outputs_for_configs(
    video_base_dir: str,
    segments: Iterable[RouteSegment],
    config_ids: Iterable[str],
) -> None:
    config_id_list = list(config_ids)
    if not config_id_list:
        return

    for segment in segments:
        raw_dir = raw_segment_output_dir(video_base_dir, segment)
        for config_id in config_id_list:
            raw_path = raw_segment_video_path(video_base_dir, config_id, segment)
            if os.path.exists(raw_path):
                os.remove(raw_path)
        _remove_dir_if_empty(raw_dir)

        for final_segment in segment.planned_final_segments:
            final_dir = final_segment_output_dir(video_base_dir, final_segment)
            for config_id in config_id_list:
                final_path = final_segment_video_path(video_base_dir, config_id, final_segment)
                if os.path.exists(final_path):
                    os.remove(final_path)
            _remove_dir_if_empty(final_dir)


def _remove_dir_if_empty(path: str) -> None:
    if os.path.isdir(path) and not os.listdir(path):
        os.rmdir(path)


def cleanup_route_outputs(
    video_base_dir: str,
    segments: Iterable[RouteSegment],
    config_ids: Iterable[str] | None = None,
) -> None:
    if config_ids is not None:
        cleanup_route_outputs_for_configs(
            video_base_dir=video_base_dir,
            segments=segments,
            config_ids=config_ids,
        )
        return

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
