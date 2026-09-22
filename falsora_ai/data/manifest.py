"""
Video manifest — the single index of what data exists.
======================================================

Everything downstream (splits, extraction, datasets, evaluation) reads the
manifest rather than walking ``raw_datasets/`` itself. One scan, one source of
truth, one file to inspect when a number looks wrong.

The manifest is a CSV rather than a parquet or a pickle, deliberately. It is
7,718 rows, it is the artefact a supervisor is most likely to want to open, and
it should stay readable with no dependencies beyond a text editor. It is small
enough to commit, which also makes the splits auditable in a pull request diff.

Design notes
------------
*Labels come from the directory, never from a metadata file.* Celeb-DF ships
``List_of_testing_videos.txt`` whose first column is ``1`` for **real** and
``0`` for **fake** — the opposite of the convention used everywhere else in this
project. Reading that column as a label would invert 518 videos and produce an
evaluation number that looks plausible and is exactly wrong. The list is used
only as a *membership filter*; labels are derived from the source directory, and
:func:`load_celebdf_test_list` asserts the two agree.

*Held-out sources are restricted to the official test list.* Extracting the
other ~5,700 Celeb-DF videos would cost hours of CPU for data we have committed
never to train on.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from falsora_ai.config import DataConfig
from falsora_ai.data.identity import identities_for

__all__ = [
    "VideoRecord",
    "MANIFEST_VERSION",
    "build_manifest",
    "write_manifest",
    "read_manifest",
    "load_celebdf_test_list",
    "summarise",
]

# Bumped whenever the column set or the meaning of a column changes, so a stale
# manifest is rejected loudly instead of being silently misinterpreted.
MANIFEST_VERSION = "1.0.0"

# Celeb-DF's list column: 1 means REAL, 0 means FAKE. Recorded here explicitly
# because the inversion is the single easiest mistake to make with this dataset.
_CELEBDF_LIST_LABEL = {"1": "real", "0": "fake"}


@dataclass(frozen=True)
class VideoRecord:
    """One video, everything the pipeline needs to know about it.

    Attributes:
        relpath: Path relative to ``raw_datasets``, POSIX separators. This is
            the primary key and is stable across machines.
        source: Source directory, matching ``DataConfig.SOURCE_LABELS``.
        domain: ``ffpp`` | ``dfd`` | ``celebdf``.
        label: ``real`` | ``fake``.
        role: ``train_pool`` | ``heldout_test``.
        identities: Every human identity appearing in the video, namespaced.
            Serialised space-separated; no identity key contains a space.
        frames: How many face crops to extract from this video.
        group: Connected-component id, filled in by :mod:`falsora_ai.data.splits`.
        split: ``train`` | ``val`` | ``test``, filled in by splits.
    """

    relpath: str
    source: str
    domain: str
    label: str
    role: str
    identities: tuple[str, ...]
    frames: int
    group: str = ""
    split: str = ""

    @property
    def video_id(self) -> str:
        """Short stable id, used for crop filenames and resumability."""
        return hashlib.sha1(self.relpath.encode("utf-8")).hexdigest()[:12]


def load_celebdf_test_list(raw_root: Path, data: DataConfig) -> set[str]:
    """Read Celeb-DF's official test list into a set of relative paths.

    Returns paths relative to ``raw_datasets`` (i.e. prefixed with
    ``Celeb DF/``) so they can be matched against ``VideoRecord.relpath``.

    Raises:
        FileNotFoundError: If the list is missing.
        ValueError: If the list's own label column disagrees with the label
            implied by the directory — which would mean either the file is
            corrupt or our understanding of its convention is wrong. Either way
            it must stop the build.
    """
    list_path = raw_root / data.celebdf_test_list
    if not list_path.exists():
        raise FileNotFoundError(
            f"Celeb-DF test list not found at {list_path}. It defines the "
            "held-out benchmark; without it the cross-dataset number is not "
            "comparable to published results."
        )

    wanted: set[str] = set()
    for lineno, raw in enumerate(list_path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"{list_path}:{lineno}: expected '<label> <path>', got {line!r}")
        flag, rel = parts
        if flag not in _CELEBDF_LIST_LABEL:
            raise ValueError(f"{list_path}:{lineno}: unexpected label flag {flag!r}")

        source = f"Celeb DF/{rel.split('/')[0]}"
        expected = data.SOURCE_LABELS.get(source)
        if expected is None:
            raise ValueError(f"{list_path}:{lineno}: unknown source directory in {rel!r}")
        if _CELEBDF_LIST_LABEL[flag] != expected:
            raise ValueError(
                f"{list_path}:{lineno}: list says {_CELEBDF_LIST_LABEL[flag]!r} but "
                f"directory {source!r} means {expected!r}. Celeb-DF uses 1=real/0=fake; "
                "if that has changed, _CELEBDF_LIST_LABEL must be updated deliberately."
            )
        wanted.add(f"Celeb DF/{rel}")
    return wanted


def build_manifest(raw_root: Path, data: DataConfig | None = None) -> list[VideoRecord]:
    """Scan ``raw_root`` and return one :class:`VideoRecord` per usable video.

    Sources listed in ``EXCLUDED_SOURCES`` are skipped entirely. Held-out
    sources are filtered to the official test list when
    ``celebdf_use_official_list_only`` is set.

    Raises:
        FileNotFoundError: If ``raw_root`` or a declared source is missing —
            silently producing a short manifest would look like a smaller
            dataset rather than a misconfiguration.
        IdentityParseError: If any filename breaks its source's convention.
    """
    data = data or DataConfig()
    raw_root = Path(raw_root)
    if not raw_root.is_dir():
        raise FileNotFoundError(f"raw_datasets not found at {raw_root}")

    heldout_filter: set[str] | None = None
    if data.celebdf_use_official_list_only:
        heldout_filter = load_celebdf_test_list(raw_root, data)

    records: list[VideoRecord] = []
    for source, label in data.SOURCE_LABELS.items():
        if source in data.EXCLUDED_SOURCES:
            continue

        src_dir = raw_root / source
        if not src_dir.is_dir():
            raise FileNotFoundError(
                f"Source {source!r} declared in SOURCE_LABELS but not found at {src_dir}"
            )

        domain = data.domain_of[source]
        role = data.role_of(source)
        n_frames = data.frames_for(source)

        for path in sorted(src_dir.iterdir()):
            if path.suffix.lower() not in data.video_extensions:
                continue
            relpath = f"{source}/{path.name}"

            if (
                role == "heldout_test"
                and heldout_filter is not None
                and relpath not in heldout_filter
            ):
                continue

            records.append(
                VideoRecord(
                    relpath=relpath,
                    source=source,
                    domain=domain,
                    label=label,
                    role=role,
                    identities=identities_for(source, path.name),
                    frames=n_frames,
                )
            )

    if not records:
        raise FileNotFoundError(f"No videos found under {raw_root}")
    return records


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

_COLUMNS = [f.name for f in fields(VideoRecord)]


def write_manifest(records: list[VideoRecord], path: Path) -> Path:
    """Write the manifest to CSV, sorted by ``relpath`` for a stable diff."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        fh.write(f"# falsora manifest v{MANIFEST_VERSION}\n")
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
        writer.writeheader()
        for rec in sorted(records, key=lambda r: r.relpath):
            row = asdict(rec)
            row["identities"] = " ".join(rec.identities)
            writer.writerow(row)
    return path


def read_manifest(path: Path) -> list[VideoRecord]:
    """Read a manifest back, refusing one written by an incompatible version."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        header = fh.readline()
        if not header.startswith("# falsora manifest v"):
            raise ValueError(f"{path} is not a falsora manifest (missing version banner)")
        version = header.split("v", 1)[1].strip()
        if version.split(".")[0] != MANIFEST_VERSION.split(".")[0]:
            raise ValueError(
                f"{path} is manifest v{version}; this code writes v{MANIFEST_VERSION}. "
                "Rebuild it rather than reinterpreting the columns."
            )
        return [
            VideoRecord(
                relpath=row["relpath"],
                source=row["source"],
                domain=row["domain"],
                label=row["label"],
                role=row["role"],
                identities=tuple(row["identities"].split()) if row["identities"] else (),
                frames=int(row["frames"]),
                group=row["group"],
                split=row["split"],
            )
            for row in csv.DictReader(fh)
        ]


def summarise(records: list[VideoRecord]) -> str:
    """Human-readable breakdown, printed by the CLI and pasted into the report."""
    from collections import defaultdict

    by: dict[tuple[str, str, str], list[VideoRecord]] = defaultdict(list)
    for r in records:
        by[(r.role, r.domain, r.label)].append(r)

    lines = [
        f"{'role':<14}{'domain':<10}{'label':<7}{'videos':>8}{'crops':>10}",
        "-" * 49,
    ]
    totals: dict[str, int] = defaultdict(int)
    for key in sorted(by):
        role, domain, label = key
        group = by[key]
        crops = sum(r.frames for r in group)
        lines.append(f"{role:<14}{domain:<10}{label:<7}{len(group):>8}{crops:>10,}")
        totals[f"{role}/{label}"] += crops

    lines.append("-" * 49)
    for role in ("train_pool", "heldout_test"):
        real, fake = totals[f"{role}/real"], totals[f"{role}/fake"]
        if not (real or fake):
            continue
        ratio = f"{fake / real:.2f}" if real else "n/a"
        lines.append(f"{role:<14}real={real:>8,}  fake={fake:>8,}  fake:real={ratio}")
    lines.append(f"{'TOTAL':<14}videos={len(records):,}  crops={sum(r.frames for r in records):,}")
    return "\n".join(lines)
