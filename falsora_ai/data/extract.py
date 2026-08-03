"""
Face crop extraction — the slow, resumable stage.
=================================================

Turns 7,718 videos into ~97,000 face crops on disk. On a 4-core laptop CPU this
is several hours, which drives most of the design here.

Resumability
------------
A run that cannot be interrupted will be interrupted. Progress is journalled to
a JSONL ledger, one line appended per completed video, flushed immediately. On
restart, videos already in the ledger are skipped, so closing the laptop costs
minutes rather than the whole run.

The ledger is append-only and never rewritten, so a crash mid-write can corrupt
at most the final line — which :func:`load_ledger` discards rather than
refusing to start.

Failures are recorded, not raised
---------------------------------
A video with no detectable face is a fact about the dataset, not an error. It is
written to the ledger with ``status="no_face"`` and the run continues. What must
never happen is a silent drop: :func:`extraction_report` surfaces the counts, so
a detector misconfiguration that quietly discards 30% of the data shows up as a
number instead of as an unexplained accuracy gap weeks later.

Determinism
-----------
Which frames are sampled depends only on the video's frame count, so two runs
produce identical crops. Crop filenames embed the source frame index, making
every crop traceable back to a timestamp in a specific video — necessary for
the forensic evidence trail that module 6.7 has to produce.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from falsora_ai.common.faces import FaceDetector, crop_face
from falsora_ai.common.video import (
    VideoReadError,
    probe_frame_count,
    read_frames,
    sample_frame_indices,
)
from falsora_ai.config import Config
from falsora_ai.data.manifest import VideoRecord

__all__ = [
    "LEDGER_NAME",
    "CROP_INDEX_NAME",
    "ExtractionResult",
    "crop_dir_for",
    "crop_name",
    "load_ledger",
    "append_ledger",
    "extract_video",
    "extract_all",
    "extraction_report",
    "write_crop_index",
]

LEDGER_NAME = "_extraction_ledger.jsonl"
CROP_INDEX_NAME = "crops.csv"


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome for one video.

    ``status`` is one of:
        ``ok``          — at least one crop written
        ``no_face``     — decoded fine, detector found nothing usable
        ``unreadable``  — the file could not be decoded
    """

    relpath: str
    status: str
    crops: tuple[str, ...] = ()
    frames_requested: int = 0
    detail: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "relpath": self.relpath,
                "status": self.status,
                "crops": list(self.crops),
                "frames_requested": self.frames_requested,
                "detail": self.detail,
            },
            ensure_ascii=False,
        )


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


def crop_dir_for(root: Path, record: VideoRecord) -> Path:
    """``face_crops/<split>/<label>/``.

    Splitting the directory tree by split as well as label means a training run
    physically cannot read the test set: a wrong path yields an empty directory
    and a loud failure, rather than a quietly contaminated dataset.
    """
    return Path(root) / record.split / record.label


def crop_name(record: VideoRecord, frame_index: int) -> str:
    """Stable, traceable crop filename: ``<video_id>_f<frame>.jpg``.

    ``video_id`` is a hash of the source path, so the name is short and safe
    even though original filenames contain spaces and ``++``.
    """
    return f"{record.video_id}_f{frame_index:05d}.jpg"


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------


def load_ledger(path: Path) -> dict[str, ExtractionResult]:
    """Read the ledger, tolerating a truncated final line from a hard kill."""
    path = Path(path)
    if not path.exists():
        return {}

    out: dict[str, ExtractionResult] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # partial write from an interrupted run; re-done below
        out[row["relpath"]] = ExtractionResult(
            relpath=row["relpath"],
            status=row["status"],
            crops=tuple(row.get("crops", ())),
            frames_requested=row.get("frames_requested", 0),
            detail=row.get("detail", ""),
        )
    return out


def append_ledger(path: Path, result: ExtractionResult) -> None:
    """Append one result and flush to the OS immediately.

    Without the flush, a crash loses whatever is sitting in Python's buffer and
    those videos are re-extracted — wasteful but harmless. With it, the ledger
    is accurate to the last completed video.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(result.to_json() + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def extract_video(
    record: VideoRecord,
    raw_root: Path,
    crops_root: Path,
    detector: FaceDetector,
    cfg: Config,
    *,
    overwrite: bool = False,
) -> ExtractionResult:
    """Extract face crops from one video. Never raises for data problems."""
    import cv2  # local import: extraction needs OpenCV, importers of this module may not

    source = Path(raw_root) / record.relpath
    out_dir = crop_dir_for(crops_root, record)

    try:
        total = probe_frame_count(source)
        if total <= 0:
            return ExtractionResult(
                record.relpath, "unreadable", detail="frame count unavailable"
            )
        indices = sample_frame_indices(total, record.frames)
        frames = list(read_frames(source, indices))
    except (VideoReadError, OSError) as exc:
        return ExtractionResult(record.relpath, "unreadable", detail=str(exc))

    if not frames:
        return ExtractionResult(record.relpath, "unreadable", detail="no frames decoded")

    boxes = detector.detect_batch([frame for _, frame in frames])

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    # strict=True: one box per frame is an invariant of FaceDetector.
    for (frame_index, frame), box in zip(frames, boxes, strict=True):
        if box is None:
            continue
        path = out_dir / crop_name(record, frame_index)
        if path.exists() and not overwrite:
            written.append(str(path))
            continue
        try:
            crop = crop_face(frame, box, cfg.face)
        except ValueError:
            continue  # degenerate box; one lost frame, not a lost video
        cv2.imwrite(
            str(path),
            cv2.cvtColor(crop, cv2.COLOR_RGB2BGR),
            [cv2.IMWRITE_JPEG_QUALITY, cfg.face.jpeg_quality],
        )
        written.append(str(path))

    if not written:
        return ExtractionResult(
            record.relpath,
            "no_face",
            frames_requested=len(indices),
            detail=f"no face passed conf>={cfg.face.min_confidence} "
            f"size>={cfg.face.min_face_size}px in {len(frames)} frames",
        )
    return ExtractionResult(
        record.relpath,
        "ok",
        crops=tuple(written),
        frames_requested=len(indices),
    )


def extract_all(
    records: Iterable[VideoRecord],
    cfg: Config,
    *,
    detector: FaceDetector | None = None,
    resume: bool = True,
    progress: bool = True,
) -> dict[str, ExtractionResult]:
    """Extract every record, skipping those already in the ledger.

    Single-process by design. MTCNN already saturates the available cores
    through torch's own threading, and running several detector instances in
    parallel on a 4-core laptop makes it slower, not faster, while multiplying
    memory. If a many-core machine becomes available, parallelise over videos
    here — the ledger makes that safe, since each video is independent.
    """
    records = list(records)
    ledger_path = cfg.paths.face_crops / LEDGER_NAME
    done = load_ledger(ledger_path) if resume else {}

    todo = [r for r in records if r.relpath not in done]
    if progress:
        print(
            f"{len(records):,} videos in manifest · {len(done):,} already done · "
            f"{len(todo):,} to extract"
        )
    if not todo:
        return done

    if detector is None:
        from falsora_ai.common.faces import MTCNNDetector
        from falsora_ai.config import resolve_device

        detector = MTCNNDetector(cfg.face, device=resolve_device())

    results = dict(done)
    for i, record in enumerate(todo, start=1):
        result = extract_video(
            record, cfg.paths.raw_datasets, cfg.paths.face_crops, detector, cfg
        )
        append_ledger(ledger_path, result)
        results[record.relpath] = result
        if progress and (i % 25 == 0 or i == len(todo)):
            counts = Counter(r.status for r in results.values())
            print(
                f"  [{i:>5}/{len(todo)}] ok={counts['ok']:,} "
                f"no_face={counts['no_face']:,} unreadable={counts['unreadable']:,}",
                flush=True,
            )
    return results


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def extraction_report(
    records: list[VideoRecord], results: dict[str, ExtractionResult]
) -> str:
    """Per-split yield, and a warning when losses are high enough to bias things."""
    by_split: dict[str, Counter] = {}
    crops_by_split: Counter = Counter()
    for rec in records:
        res = results.get(rec.relpath)
        status = res.status if res else "pending"
        by_split.setdefault(rec.split, Counter())[f"{rec.label}/{status}"] += 1
        if res and res.status == "ok":
            crops_by_split[rec.split] += len(res.crops)

    lines = ["Extraction yield", "-" * 60]
    for split in sorted(by_split):
        counts = by_split[split]
        detail = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        lines.append(f"{split:<10} crops={crops_by_split[split]:>8,}  {detail}")

    total = len(records)
    lost = sum(
        1 for r in records if (results.get(r.relpath) or ExtractionResult(r.relpath, "pending")).status in {"no_face", "unreadable"}
    )
    lines.append("-" * 60)
    lines.append(f"videos lost to no_face/unreadable: {lost:,} / {total:,} ({lost / total:.1%})")
    if total and lost / total > 0.05:
        lines.append(
            "WARNING: >5% of videos yielded nothing. Detection loss is rarely "
            "uniform across classes — check the per-label counts above before "
            "training, because a detector that fails more often on one class "
            "shifts the class balance the frame budget was tuned for."
        )
    return "\n".join(lines)


def write_crop_index(
    records: list[VideoRecord],
    results: dict[str, ExtractionResult],
    path: Path,
) -> Path:
    """Write one row per crop: the file the Dataset in M2 reads directly.

    Carrying split, label, domain and source video on every row means the
    Dataset needs no joins and no knowledge of the directory layout, and every
    prediction can be traced back to its source video for the evidence trail.
    """
    import csv

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    by_relpath = {r.relpath: r for r in records}

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["crop_path", "split", "label", "domain", "source", "group", "video_relpath"]
        )
        for relpath, result in sorted(results.items()):
            if result.status != "ok":
                continue
            rec = by_relpath.get(relpath)
            if rec is None:
                continue  # ledger entry for a video no longer in the manifest
            for crop in result.crops:
                writer.writerow(
                    [
                        crop,
                        rec.split,
                        rec.label,
                        rec.domain,
                        rec.source,
                        rec.group,
                        rec.relpath,
                    ]
                )
    return path
