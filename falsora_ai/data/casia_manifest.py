"""
CASIA v2.0 manifest — the single index of what tampering-branch data exists.
=============================================================================

Mirrors :mod:`falsora_ai.data.manifest`'s contract but for images rather than
videos: one scan, one CSV, everything downstream (splits, the future Dataset,
evaluation) reads this rather than walking ``raw_datasets/CASIA2`` itself.

Design notes
------------
*Labels come from the directory, never inferred from the filename.* ``Au/`` is
authentic, ``Tp/`` is tampered — that is CASIA v2.0's own convention and there
is no ambiguity to resolve, unlike Celeb-DF's inverted test-list column.

*Every tampered image must have a ground-truth mask.* CASIA v2.0 ships exactly
one PNG mask per ``Tp`` image, usually named ``<Tp stem>_gt.png`` — but the
dataset itself is inconsistent about it: 142 of the 5,123 masks have a typo'd
source id or an ``S``/``D`` splice flag that disagrees with their Tp image
(e.g. ``Tp_D_CNN..._arc00086_arc00086_00306.tif`` ships as
``..._arc00086_xxx00000_00306_gt.png``), and one ships as ``..._gt3.png``
instead of ``..._gt.png``. The trailing sequence number (``00306``) is the one
part of the name CASIA never gets wrong, so masks are matched on that, with
the exact-stem name tried first since it is unambiguous when present. A
missing mask even after that fallback means a genuinely corrupt download, and
training the localisation head on a silently absent mask would be worse than
failing loudly here.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from falsora_ai.config import TamperingConfig
from falsora_ai.data.casia_identity import au_source, tp_sources

__all__ = [
    "ImageRecord",
    "CASIA_MANIFEST_VERSION",
    "build_casia_manifest",
    "write_casia_manifest",
    "read_casia_manifest",
    "summarise_casia",
]

CASIA_MANIFEST_VERSION = "1.0.0"


@dataclass(frozen=True)
class ImageRecord:
    """One CASIA v2.0 image, everything the tampering branch needs to know.

    Attributes:
        relpath: Path relative to the CASIA root (``Au/...`` or ``Tp/...``),
            POSIX separators. Primary key, stable across machines.
        label: ``authentic`` | ``tampered``.
        sources: Source-image id(s) this image is built from, namespaced
            ``casia:<category><n>``. An authentic image carries its own id; a
            tampered image carries the one or two ids it was spliced or
            copy-moved from. Serialised space-separated.
        mask_relpath: Ground-truth mask path relative to the CASIA root, or
            ``""`` for authentic images (which have none).
        group: Connected-component id, filled in by
            :mod:`falsora_ai.data.casia_splits`.
        split: ``train`` | ``val`` | ``test``, filled in by casia_splits.
    """

    relpath: str
    label: str
    sources: tuple[str, ...]
    mask_relpath: str = ""
    group: str = ""
    split: str = ""

    @property
    def image_id(self) -> str:
        """Short stable id — mirrors ``VideoRecord.video_id``'s role."""
        return hashlib.sha1(self.relpath.encode("utf-8")).hexdigest()[:12]


def _mask_name(tp_filename: str) -> str:
    """``Tp_..._00138.tif`` → ``Tp_..._00138_gt.png``, CASIA's usual convention."""
    return f"{Path(tp_filename).stem}_gt.png"


_SEQ_RE = re.compile(r"_(\d+)\.[A-Za-z]+$")
_GT_SEQ_RE = re.compile(r"_(\d+)_gt\d*\.png$")


def _sequence_number(filename: str) -> str | None:
    """Trailing sequence number, the one part of a CASIA filename that is
    never mistyped — used as the fallback key when a mask's name otherwise
    disagrees with its Tp image (see module docstring)."""
    match = _SEQ_RE.search(filename) or _GT_SEQ_RE.search(filename)
    return match.group(1) if match else None


def _index_masks_by_sequence(gt_dir: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    for path in gt_dir.iterdir():
        seq = _sequence_number(path.name)
        if seq is not None:
            index[seq] = path.name
    return index


def build_casia_manifest(
    casia_root: Path, cfg: TamperingConfig | None = None
) -> list[ImageRecord]:
    """Scan ``casia_root`` (``raw_datasets/CASIA2``) and index every image.

    Raises:
        FileNotFoundError: If the root, a declared subdirectory, or a Tp
            image's ground-truth mask is missing.
        IdentityParseError: If a filename breaks its directory's naming
            convention.
    """
    cfg = cfg or TamperingConfig()
    casia_root = Path(casia_root)
    if not casia_root.is_dir():
        raise FileNotFoundError(f"CASIA v2.0 not found at {casia_root}")

    au_dir = casia_root / cfg.au_dir
    tp_dir = casia_root / cfg.tp_dir
    gt_dir = casia_root / cfg.gt_dir
    for d in (au_dir, tp_dir, gt_dir):
        if not d.is_dir():
            raise FileNotFoundError(f"Expected CASIA subdirectory missing: {d}")

    records: list[ImageRecord] = []

    for path in sorted(au_dir.iterdir()):
        if path.suffix.lower() not in cfg.image_extensions:
            continue
        records.append(
            ImageRecord(
                relpath=f"{cfg.au_dir}/{path.name}",
                label="authentic",
                sources=au_source(path.name),
            )
        )

    masks_by_sequence = _index_masks_by_sequence(gt_dir)
    for path in sorted(tp_dir.iterdir()):
        if path.suffix.lower() not in cfg.tampered_extensions:
            continue
        mask_name = _mask_name(path.name)
        if not (gt_dir / mask_name).exists():
            seq = _sequence_number(path.name)
            fallback = masks_by_sequence.get(seq) if seq else None
            if fallback is None:
                raise FileNotFoundError(
                    f"No ground-truth mask for {path.name}: expected {gt_dir / mask_name}"
                )
            mask_name = fallback
        records.append(
            ImageRecord(
                relpath=f"{cfg.tp_dir}/{path.name}",
                label="tampered",
                sources=tp_sources(path.name),
                mask_relpath=f"{cfg.gt_dir}/{mask_name}",
            )
        )

    if not records:
        raise FileNotFoundError(f"No CASIA images found under {casia_root}")
    return records


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

_COLUMNS = [f.name for f in fields(ImageRecord)]


def write_casia_manifest(records: list[ImageRecord], path: Path) -> Path:
    """Write the manifest to CSV, sorted by ``relpath`` for a stable diff."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        fh.write(f"# falsora casia manifest v{CASIA_MANIFEST_VERSION}\n")
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
        writer.writeheader()
        for rec in sorted(records, key=lambda r: r.relpath):
            row = asdict(rec)
            row["sources"] = " ".join(rec.sources)
            writer.writerow(row)
    return path


def read_casia_manifest(path: Path) -> list[ImageRecord]:
    """Read a manifest back, refusing one written by an incompatible version."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        header = fh.readline()
        if not header.startswith("# falsora casia manifest v"):
            raise ValueError(f"{path} is not a falsora CASIA manifest (missing version banner)")
        version = header.split("v", 1)[1].strip()
        if version.split(".")[0] != CASIA_MANIFEST_VERSION.split(".")[0]:
            raise ValueError(
                f"{path} is manifest v{version}; this code writes v{CASIA_MANIFEST_VERSION}. "
                "Rebuild it rather than reinterpreting the columns."
            )
        return [
            ImageRecord(
                relpath=row["relpath"],
                label=row["label"],
                sources=tuple(row["sources"].split()) if row["sources"] else (),
                mask_relpath=row["mask_relpath"],
                group=row["group"],
                split=row["split"],
            )
            for row in csv.DictReader(fh)
        ]


def summarise_casia(records: list[ImageRecord]) -> str:
    """Human-readable breakdown, printed by the CLI."""
    by_label: dict[str, list[ImageRecord]] = defaultdict(list)
    for r in records:
        by_label[r.label].append(r)

    lines = [f"{'label':<12}{'images':>8}", "-" * 20]
    for label in sorted(by_label):
        lines.append(f"{label:<12}{len(by_label[label]):>8}")
    lines.append("-" * 20)
    lines.append(f"{'TOTAL':<12}{len(records):>8}")
    return "\n".join(lines)
