#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.route_segments import RouteSegment, build_route_segments

DEFAULT_ROUTE_ROOT = PROJECT_ROOT / "routes" / "natlan"

LEGACY_DIR_PATTERN = re.compile(
    r"^(?P<country>[a-z]+)_(?P<old_index>\d+)_(?P<route_prefix>[hr])(?P<route_suffix>\d+)$"
)
SEGMENT_DIR_PATTERN = re.compile(r"^(?P<country>[a-z]+)_r(?P<route_suffix>\d{2})_s(?P<segment_index>\d{2})$")
TARGET_DIR_PATTERN = re.compile(
    r"^(?P<country>[a-z]+)_r(?P<route_suffix>\d{2})_(?P<label>[a-z_]+)(?P<occurrence>\d{2})$"
)


def _default_base_dir() -> Path:
    candidates = [
        PROJECT_ROOT / "recordings",
        PROJECT_ROOT.parent / "recordings",
        PROJECT_ROOT.parent / "Recordings",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return PROJECT_ROOT / "recordings"


DEFAULT_BASE_DIR = _default_base_dir()


@dataclass(frozen=True)
class RecordingDir:
    recording_root: Path
    label: str
    path: Path
    country: str
    route_suffix: int
    source_order: int
    earliest_mtime: float
    file_count: int
    source_kind: str


@dataclass(frozen=True)
class PlannedRename:
    source: RecordingDir
    target_path: Path
    target_segment: RouteSegment


@dataclass(frozen=True)
class RouteAudit:
    recording_root: Path
    route_suffix: int
    expected_segments: Sequence[RouteSegment]
    actual_labels: Sequence[str]
    renames: Sequence[PlannedRename]
    extras: Sequence[RecordingDir]
    missing_labels: Sequence[str]


def _iter_route_suffixes(route_root: Path) -> List[int]:
    suffixes: List[int] = []
    for route_path in route_root.glob("*.py"):
        if route_path.stem.isdigit():
            suffixes.append(int(route_path.stem))
    return sorted(suffixes)


def _load_route_segments(route_root: Path, route_suffix: int) -> Optional[List[RouteSegment]]:
    route_path = route_root / f"{route_suffix}.py"
    if not route_path.exists():
        return None

    spec = importlib.util.spec_from_file_location(f"natlan_route_{route_suffix}", route_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load route module from {route_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return build_route_segments(module.ROUTE, "natlan", route_suffix)


def _collect_valid_labels(route_root: Path) -> Set[str]:
    labels: Set[str] = set()
    for route_suffix in _iter_route_suffixes(route_root):
        segments = _load_route_segments(route_root, route_suffix)
        if segments is None:
            continue
        labels.update(segment.label_name for segment in segments)
    return labels


def _looks_like_recording_root(path: Path, valid_labels: Set[str]) -> bool:
    if not path.is_dir():
        return False
    for child in path.iterdir():
        if child.is_dir() and child.name in valid_labels:
            return True
    return False


def _discover_recording_roots(base_dir: Path, valid_labels: Set[str]) -> List[Path]:
    if _looks_like_recording_root(base_dir, valid_labels):
        return [base_dir]

    roots: List[Path] = []
    for child in sorted(base_dir.iterdir()):
        if _looks_like_recording_root(child, valid_labels):
            roots.append(child)
    return roots


def _iter_recording_dirs(recording_root: Path) -> Iterable[RecordingDir]:
    for label_dir in sorted(recording_root.iterdir()):
        if not label_dir.is_dir() or label_dir.name.startswith("."):
            continue

        for child in sorted(label_dir.iterdir()):
            if not child.is_dir():
                continue
            target_match = TARGET_DIR_PATTERN.match(child.name)
            if target_match is not None and target_match.group("label") == label_dir.name:
                continue

            file_paths = sorted(path for path in child.iterdir() if path.is_file())
            earliest_mtime = min((path.stat().st_mtime for path in file_paths), default=child.stat().st_mtime)
            legacy_match = LEGACY_DIR_PATTERN.match(child.name)
            if legacy_match is not None:
                yield RecordingDir(
                    recording_root=recording_root,
                    label=label_dir.name,
                    path=child,
                    country=legacy_match.group("country"),
                    route_suffix=int(legacy_match.group("route_suffix")),
                    source_order=int(legacy_match.group("old_index")),
                    earliest_mtime=earliest_mtime,
                    file_count=len(file_paths),
                    source_kind="legacy",
                )
                continue

            segment_match = SEGMENT_DIR_PATTERN.match(child.name)
            if segment_match is not None:
                yield RecordingDir(
                    recording_root=recording_root,
                    label=label_dir.name,
                    path=child,
                    country=segment_match.group("country"),
                    route_suffix=int(segment_match.group("route_suffix")),
                    source_order=int(segment_match.group("segment_index")),
                    earliest_mtime=earliest_mtime,
                    file_count=len(file_paths),
                    source_kind="segment",
                )


def _align_route_items(
    items: Sequence[RecordingDir], expected_segments: Sequence[RouteSegment]
) -> Tuple[List[Tuple[RecordingDir, RouteSegment]], List[RecordingDir], List[str]]:
    expected_labels = [segment.label_name for segment in expected_segments]
    actual_labels = [item.label for item in items]
    dp = [[0] * (len(expected_labels) + 1) for _ in range(len(actual_labels) + 1)]

    for i in range(len(actual_labels) - 1, -1, -1):
        for j in range(len(expected_labels) - 1, -1, -1):
            if actual_labels[i] == expected_labels[j]:
                dp[i][j] = 1 + dp[i + 1][j + 1]
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])

    matched_pairs: List[Tuple[RecordingDir, RouteSegment]] = []
    matched_actual_indices = set()
    matched_expected_indices = set()
    i = 0
    j = 0
    while i < len(actual_labels) and j < len(expected_labels):
        if actual_labels[i] == expected_labels[j] and dp[i][j] == 1 + dp[i + 1][j + 1]:
            matched_pairs.append((items[i], expected_segments[j]))
            matched_actual_indices.add(i)
            matched_expected_indices.add(j)
            i += 1
            j += 1
            continue

        if dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1

    extras = [item for index, item in enumerate(items) if index not in matched_actual_indices]
    missing_labels = [expected_labels[index] for index in range(len(expected_labels)) if index not in matched_expected_indices]
    return matched_pairs, extras, missing_labels


def _build_route_audits(base_dir: Path, route_root: Path) -> List[RouteAudit]:
    valid_labels = _collect_valid_labels(route_root)
    recording_roots = _discover_recording_roots(base_dir, valid_labels)
    if not recording_roots:
        raise FileNotFoundError(
            f"No recording roots found under {base_dir}. "
            "Expected either <recordings>/<label>/... or <recordings>/<device>/<label>/..."
        )

    items_by_route: Dict[Tuple[Path, int], List[RecordingDir]] = defaultdict(list)
    for recording_root in recording_roots:
        for item in _iter_recording_dirs(recording_root):
            items_by_route[(recording_root, item.route_suffix)].append(item)

    audits: List[RouteAudit] = []
    for (recording_root, route_suffix) in sorted(items_by_route):
        items = sorted(
            items_by_route[(recording_root, route_suffix)],
            key=lambda item: (
                0 if item.source_kind == "segment" else 1,
                item.source_order if item.source_kind == "segment" else 0,
                item.earliest_mtime,
                item.source_order if item.source_kind == "legacy" else 0,
                item.label,
                item.path.name,
            ),
        )
        expected_segments = _load_route_segments(route_root, route_suffix)
        if expected_segments is None:
            raise FileNotFoundError(
                f"Route file not found for suffix {route_suffix}: {route_root / f'{route_suffix}.py'}"
            )

        matched_pairs, extras, missing_labels = _align_route_items(items, expected_segments)
        renames: List[PlannedRename] = []
        for item, target_segment in matched_pairs:
            renames.append(
                PlannedRename(
                    source=item,
                    target_path=item.path.parent / target_segment.segment_dir_name,
                    target_segment=target_segment,
                )
            )
        audits.append(
            RouteAudit(
                recording_root=recording_root,
                route_suffix=route_suffix,
                expected_segments=tuple(expected_segments),
                actual_labels=tuple(item.label for item in items),
                renames=tuple(renames),
                extras=tuple(extras),
                missing_labels=tuple(missing_labels),
            )
        )
    return audits


def _validate_plans(plans: Sequence[PlannedRename]) -> None:
    targets: Dict[Path, PlannedRename] = {}
    for plan in plans:
        existing = targets.get(plan.target_path)
        if existing is not None:
            raise ValueError(
                f"Target collision: {existing.source.path} and {plan.source.path} -> {plan.target_path}"
            )
        targets[plan.target_path] = plan

        if plan.target_path.exists() and plan.target_path != plan.source.path:
            raise ValueError(
                f"Target already exists: {plan.target_path}. "
                f"Please move it away before renaming {plan.source.path}."
            )


def _print_summary(audits: Sequence[RouteAudit]) -> None:
    for audit in audits:
        actual_counts = sorted(
            {plan.source.file_count for plan in audit.renames} | {item.file_count for item in audit.extras}
        )
        status = "ok"
        if audit.extras:
            status = "extra"
        elif audit.missing_labels:
            status = "missing"
        expected_labels = [segment.label_name for segment in audit.expected_segments]
        print(
            f"[ROOT {audit.recording_root.name}][ROUTE {audit.route_suffix:02d}] {status} "
            f"expected={expected_labels} actual={list(audit.actual_labels)} files={actual_counts}"
        )
        if audit.extras:
            print("  extra dirs:")
            for item in audit.extras:
                print(f"    {item.path}")
        if audit.missing_labels:
            print(f"  missing labels: {list(audit.missing_labels)}")
        if len(actual_counts) > 1:
            print("  warning: mixed file counts detected, likely contains partial or interrupted recordings.")


def _print_plan(plans: Sequence[PlannedRename]) -> None:
    for plan in plans:
        print(f"{plan.source.path} -> {plan.target_path}")


def _apply(plans: Sequence[PlannedRename]) -> None:
    for plan in plans:
        plan.source.path.rename(plan.target_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rename recording directories into natlan_rXX_<label><nn> format for v5. "
            "The input can be either a single device root or the top-level recordings directory."
        )
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DEFAULT_BASE_DIR,
        help=f"Recording root to scan. Default: {DEFAULT_BASE_DIR}",
    )
    parser.add_argument(
        "--route-root",
        type=Path,
        default=DEFAULT_ROUTE_ROOT,
        help=f"Route directory used for validation. Default: {DEFAULT_ROUTE_ROOT}",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename directories. Without this flag the script only prints the plan.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = args.base_dir.expanduser().resolve()
    route_root = args.route_root.expanduser().resolve()

    if not base_dir.exists():
        raise FileNotFoundError(f"Recording directory not found: {base_dir}")
    if not route_root.exists():
        raise FileNotFoundError(f"Route directory not found: {route_root}")

    audits = _build_route_audits(base_dir, route_root)
    plans = [plan for audit in audits for plan in audit.renames]
    routes_with_extras = [audit for audit in audits if audit.extras]
    routes_with_missing = [audit for audit in audits if audit.missing_labels]

    if not plans and not routes_with_extras and not routes_with_missing:
        print(f"No old-format recording directories found under {base_dir}")
        return 0

    _validate_plans(plans)
    print(f"[INFO] base_dir={base_dir}")
    print(f"[INFO] route_root={route_root}")
    print(f"[INFO] planned renames={len(plans)}")
    print(f"[INFO] routes with extras={len(routes_with_extras)}")
    print(f"[INFO] routes with missing labels={len(routes_with_missing)}")
    _print_summary(audits)
    print()
    _print_plan(plans)

    if routes_with_extras:
        print("\n[MISMATCH] Some existing directories do not match current route definitions.")
        print("Delete or move the listed extra directories first, then rerun this script.")
        if args.apply:
            print("[ABORT] Refusing to rename while mismatched routes still exist.")
            return 1

    if routes_with_missing:
        print("\n[WARN] Some routes are missing expected segments.")
        print("Existing matching directories will still be renamed.")

    if not args.apply:
        print("\n[DRY-RUN] Add --apply to perform the renames.")
        return 0

    _apply(plans)
    print(f"\n[DONE] Renamed {len(plans)} directories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
