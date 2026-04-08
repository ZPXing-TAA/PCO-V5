from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from engine.binary_resolver import (
    describe_ffmpeg_resolution,
    describe_ffprobe_resolution,
    ffmpeg_install_hint,
)
from engine.route_segments import (
    PLANNED_CLIP_LENGTH_SEC,
    RouteSegment,
    final_segment_output_dir,
    final_segment_video_path,
    raw_segment_output_dir,
)

DEFAULT_SHORTFALL_TOLERANCE_SEC = float(os.environ.get("AUTO_VIDEO_SHORTFALL_TOLERANCE_SEC", "0.5"))


@dataclass(frozen=True)
class SourceVideoInfo:
    config_id: str
    source_path: str
    duration_sec: float
    actual_undershoot_sec: float


@dataclass(frozen=True)
class SegmentPostprocessSummary:
    source_dir: str
    route_duration_sec: float
    planned_clip_count: int
    route_tail_drop_sec: float
    media_duration_min_sec: float
    media_duration_max_sec: float
    undershoot_count: int
    max_actual_undershoot_sec: float
    target_dirs: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def has_actual_undershoot(self) -> bool:
        return self.max_actual_undershoot_sec > 1e-9


def resolve_ffmpeg_bin() -> str:
    resolved, _source = describe_ffmpeg_resolution()
    if resolved:
        return resolved
    raise FileNotFoundError(
        "ffmpeg executable not found. "
        f"{ffmpeg_install_hint()}"
    )


def resolve_ffprobe_bin() -> str:
    resolved, _source = describe_ffprobe_resolution()
    if resolved:
        return resolved
    raise FileNotFoundError(
        "ffprobe executable not found. "
        f"{ffmpeg_install_hint()}"
    )


def ensure_postprocess_tools_available(dry_run: bool) -> None:
    resolve_ffprobe_bin()
    if not dry_run:
        resolve_ffmpeg_bin()


def probe_media_duration_sec(video_path: str) -> float:
    ffprobe_bin = resolve_ffprobe_bin()
    completed = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    text = completed.stdout.strip()
    if not text:
        raise ValueError(f"ffprobe returned empty duration for {video_path}")
    duration = float(text)
    if duration <= 0:
        raise ValueError(f"ffprobe returned non-positive duration {duration!r} for {video_path}")
    return duration


def process_segment_directory(
    video_base_dir: str,
    segment: RouteSegment,
    expected_config_ids: Sequence[str],
    dry_run: bool = False,
    shortfall_tolerance_sec: float = DEFAULT_SHORTFALL_TOLERANCE_SEC,
) -> SegmentPostprocessSummary:
    source_dir = raw_segment_output_dir(video_base_dir, segment)
    source_videos = _collect_source_videos(source_dir, expected_config_ids)
    summary = _build_segment_summary(
        source_videos=source_videos,
        segment=segment,
        video_base_dir=video_base_dir,
        shortfall_tolerance_sec=shortfall_tolerance_sec,
    )
    print_segment_postprocess_summary(segment=segment, summary=summary, dry_run=dry_run)

    if dry_run:
        return summary

    _prepare_target_dirs(video_base_dir, segment)
    try:
        for source_video in source_videos:
            _emit_segment_outputs(video_base_dir=video_base_dir, segment=segment, source_video=source_video)
    except Exception:
        _cleanup_temp_targets(
            video_base_dir=video_base_dir,
            segment=segment,
            config_ids=expected_config_ids,
        )
        raise

    _cleanup_processed_sources(source_dir=source_dir, config_ids=expected_config_ids)
    return summary


def print_segment_postprocess_summary(
    segment: RouteSegment,
    summary: SegmentPostprocessSummary,
    dry_run: bool,
) -> None:
    mode = "DRY-RUN" if dry_run else "APPLY"
    prefix = f"[POSTPROCESS][{mode}][{segment.raw_segment_dir_name}]"
    mapping = ", ".join(final_segment.segment_dir_name for final_segment in segment.planned_final_segments)
    target_dirs = ", ".join(summary.target_dirs)
    actual_undershoot = (
        f"yes ({summary.undershoot_count} files, max {_format_seconds(summary.max_actual_undershoot_sec)})"
        if summary.has_actual_undershoot
        else "no"
    )
    print(f"{prefix} source_dir={summary.source_dir}")
    print(
        f"{prefix} route_duration={_format_seconds(summary.route_duration_sec)} "
        f"planned_clips={summary.planned_clip_count} "
        f"route_tail_drop={_format_seconds(summary.route_tail_drop_sec)}"
    )
    print(
        f"{prefix} media_duration_range={_format_seconds(summary.media_duration_min_sec)}"
        f"..{_format_seconds(summary.media_duration_max_sec)} "
        f"actual_shortfall={actual_undershoot}"
    )
    print(f"{prefix} target_dirs={target_dirs}")
    print(f"{prefix} numbering={segment.raw_segment_dir_name} -> {mapping}")
    for warning in summary.warnings:
        print(f"{prefix} WARNING {warning}")


def _collect_source_videos(source_dir: str, expected_config_ids: Sequence[str]) -> List[SourceVideoInfo]:
    root = Path(source_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Recorded segment directory does not exist: {source_dir}")

    discovered = {path.stem: str(path) for path in sorted(root.glob("*.mp4"))}
    expected = list(expected_config_ids)
    missing = [config_id for config_id in expected if config_id not in discovered]
    extras = sorted(config_id for config_id in discovered if config_id not in expected)
    if missing or extras:
        raise ValueError(
            f"Recorded segment directory {source_dir} does not match expected configs. "
            f"missing={missing} extras={extras}"
        )

    source_videos: List[SourceVideoInfo] = []
    for config_id in expected:
        source_path = discovered[config_id]
        duration_sec = probe_media_duration_sec(source_path)
        source_videos.append(
            SourceVideoInfo(
                config_id=config_id,
                source_path=source_path,
                duration_sec=duration_sec,
                actual_undershoot_sec=0.0,
            )
        )
    return source_videos


def _build_segment_summary(
    source_videos: Sequence[SourceVideoInfo],
    segment: RouteSegment,
    video_base_dir: str,
    shortfall_tolerance_sec: float,
) -> SegmentPostprocessSummary:
    updated_source_videos = _attach_actual_undershoots(source_videos, segment)
    warnings: List[str] = []
    undershoot_count = sum(1 for item in updated_source_videos if item.actual_undershoot_sec > 1e-9)
    max_actual_undershoot_sec = max((item.actual_undershoot_sec for item in updated_source_videos), default=0.0)
    if max_actual_undershoot_sec > shortfall_tolerance_sec:
        offenders = [
            f"{item.config_id}={_format_seconds(item.actual_undershoot_sec)}"
            for item in updated_source_videos
            if item.actual_undershoot_sec > shortfall_tolerance_sec
        ]
        warnings.append(
            "actual recordings undershoot the planned end by more than "
            f"{_format_seconds(shortfall_tolerance_sec)}: {', '.join(offenders)}"
        )

    for item in updated_source_videos:
        _validate_source_duration(item, segment)

    return SegmentPostprocessSummary(
        source_dir=raw_segment_output_dir(video_base_dir, segment),
        route_duration_sec=segment.route_duration_sec,
        planned_clip_count=segment.planned_clip_count,
        route_tail_drop_sec=segment.planned_tail_drop_sec,
        media_duration_min_sec=min(item.duration_sec for item in updated_source_videos),
        media_duration_max_sec=max(item.duration_sec for item in updated_source_videos),
        undershoot_count=undershoot_count,
        max_actual_undershoot_sec=max_actual_undershoot_sec,
        target_dirs=tuple(
            final_segment_output_dir(video_base_dir, final_segment)
            for final_segment in segment.planned_final_segments
        ),
        warnings=tuple(warnings),
    )


def _attach_actual_undershoots(
    source_videos: Sequence[SourceVideoInfo],
    segment: RouteSegment,
) -> List[SourceVideoInfo]:
    updated: List[SourceVideoInfo] = []
    for item in source_videos:
        actual_undershoot_sec = 0.0
        if segment.route_duration_sec >= PLANNED_CLIP_LENGTH_SEC:
            actual_undershoot_sec = max(0.0, segment.planned_end_sec - item.duration_sec)
        updated.append(
            SourceVideoInfo(
                config_id=item.config_id,
                source_path=item.source_path,
                duration_sec=item.duration_sec,
                actual_undershoot_sec=actual_undershoot_sec,
            )
        )
    return updated


def _validate_source_duration(source_video: SourceVideoInfo, segment: RouteSegment) -> None:
    if segment.route_duration_sec < PLANNED_CLIP_LENGTH_SEC:
        return

    for clip_index in range(segment.planned_clip_count - 1):
        required_end_sec = (clip_index + 1) * PLANNED_CLIP_LENGTH_SEC
        if source_video.duration_sec + 1e-6 < required_end_sec:
            raise ValueError(
                f"{source_video.source_path} is too short for planned clip #{clip_index + 1} of "
                f"{segment.raw_segment_dir_name}: duration={source_video.duration_sec:.3f}s "
                f"required_end={required_end_sec:.3f}s"
            )

    final_clip_start = (segment.planned_clip_count - 1) * PLANNED_CLIP_LENGTH_SEC
    if source_video.duration_sec <= final_clip_start + 1e-6:
        raise ValueError(
            f"{source_video.source_path} ends before the final planned clip can start for "
            f"{segment.raw_segment_dir_name}: duration={source_video.duration_sec:.3f}s "
            f"required_start={final_clip_start:.3f}s"
        )


def _prepare_target_dirs(video_base_dir: str, segment: RouteSegment) -> None:
    for final_segment in segment.planned_final_segments:
        target_dir = final_segment_output_dir(video_base_dir, final_segment)
        os.makedirs(target_dir, exist_ok=True)


def _cleanup_temp_targets(
    video_base_dir: str,
    segment: RouteSegment,
    config_ids: Sequence[str],
) -> None:
    for final_segment in segment.planned_final_segments:
        target_dir = final_segment_output_dir(video_base_dir, final_segment)
        for config_id in config_ids:
            temp_target_path = f"{final_segment_video_path(video_base_dir, config_id, final_segment)}.tmp.mp4"
            if os.path.exists(temp_target_path):
                os.remove(temp_target_path)
        if os.path.isdir(target_dir) and not os.listdir(target_dir):
            os.rmdir(target_dir)


def _cleanup_processed_sources(source_dir: str, config_ids: Sequence[str]) -> None:
    for config_id in config_ids:
        source_path = os.path.join(source_dir, f"{config_id}.mp4")
        if os.path.exists(source_path):
            os.remove(source_path)
    if os.path.isdir(source_dir) and not os.listdir(source_dir):
        os.rmdir(source_dir)


def _emit_segment_outputs(video_base_dir: str, segment: RouteSegment, source_video: SourceVideoInfo) -> None:
    if segment.route_duration_sec < PLANNED_CLIP_LENGTH_SEC:
        final_segment = segment.planned_final_segments[0]
        target_path = final_segment_video_path(video_base_dir, source_video.config_id, final_segment)
        _copy_video(source_video.source_path, target_path)
        return

    for final_segment in segment.planned_final_segments:
        start_sec = (final_segment.clip_index_within_parent - 1) * PLANNED_CLIP_LENGTH_SEC
        planned_end_sec = final_segment.clip_index_within_parent * PLANNED_CLIP_LENGTH_SEC
        if final_segment.clip_index_within_parent == segment.planned_clip_count:
            end_sec = min(planned_end_sec, source_video.duration_sec)
        else:
            end_sec = planned_end_sec
        target_path = final_segment_video_path(video_base_dir, source_video.config_id, final_segment)
        _extract_clip(
            source_path=source_video.source_path,
            target_path=target_path,
            start_sec=start_sec,
            end_sec=end_sec,
        )


def _copy_video(source_path: str, target_path: str) -> None:
    temp_target_path = f"{target_path}.tmp.mp4"
    if os.path.exists(temp_target_path):
        os.remove(temp_target_path)
    shutil.copy2(source_path, temp_target_path)
    os.replace(temp_target_path, target_path)


def _extract_clip(source_path: str, target_path: str, start_sec: float, end_sec: float) -> None:
    duration_sec = end_sec - start_sec
    if duration_sec <= 1e-6:
        raise ValueError(
            f"Invalid clip window for {source_path}: start={start_sec:.3f}s end={end_sec:.3f}s"
        )

    ffmpeg_bin = resolve_ffmpeg_bin()
    temp_target_path = f"{target_path}.tmp.mp4"
    if os.path.exists(temp_target_path):
        os.remove(temp_target_path)
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            source_path,
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            temp_target_path,
        ],
        check=True,
    )
    os.replace(temp_target_path, target_path)


def _format_seconds(value: float) -> str:
    return f"{value:.3f}s"
