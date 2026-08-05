"""
Command line for the data pipeline.
===================================

    python -m falsora_ai.data manifest        # scan, split, verify, write CSV
    python -m falsora_ai.data extract         # face crops (hours; resumable)
    python -m falsora_ai.data report          # what is on disk right now

``manifest`` is fast and safe to re-run: it rebuilds the split deterministically
from the same seed, so it produces a byte-identical file unless the data on disk
has changed. ``extract`` is the slow one and can be interrupted freely.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from falsora_ai.config import Config
from falsora_ai.data.extract import (
    CROP_INDEX_NAME,
    LEDGER_NAME,
    extract_all,
    extraction_report,
    load_ledger,
    write_crop_index,
)
from falsora_ai.data.manifest import (
    VideoRecord,
    build_manifest,
    read_manifest,
    summarise,
    write_manifest,
)
from falsora_ai.data.splits import assign_splits, split_report, verify_identity_disjoint

MANIFEST_NAME = "videos.csv"


def _manifest_path(cfg: Config) -> Path:
    return cfg.paths.manifests / MANIFEST_NAME


def stratified_sample(
    records: list[VideoRecord], n: int, seed: int
) -> list[VideoRecord]:
    """Draw ``n`` videos spread evenly over every (domain, label) stratum.

    A smoke test exists to answer one question: does face detection lose
    videos, and does it lose them evenly across real and fake? The manifest is
    sorted by path, so taking the first N answers neither — N=20 lands entirely
    inside Celeb-DF's real videos, which is one class of one domain, and that
    domain is held out of training anyway. A run like that can report 100%
    yield while the detector silently fails on half of FF++'s fakes.

    Round-robin over the strata rather than sampling proportionally: the point
    is coverage of the rare combinations, not a miniature of the corpus.
    """
    if n <= 0:
        return []
    buckets: dict[tuple[str, str], list[VideoRecord]] = defaultdict(list)
    for rec in records:
        buckets[(rec.domain, rec.label)].append(rec)

    rng = random.Random(seed)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    out: list[VideoRecord] = []
    keys = sorted(buckets)
    while len(out) < n and any(buckets[k] for k in keys):
        for key in keys:
            if not buckets[key]:
                continue
            out.append(buckets[key].pop())
            if len(out) == n:
                break
    # Restore manifest order so the ledger is written in a stable sequence.
    order = {r.relpath: i for i, r in enumerate(records)}
    return sorted(out, key=lambda r: order[r.relpath])


def cmd_manifest(cfg: Config, args: argparse.Namespace) -> int:
    print(f"Scanning {cfg.paths.raw_datasets} ...")
    records = build_manifest(cfg.paths.raw_datasets, cfg.data)
    print(summarise(records))

    print("\nAssigning identity-disjoint splits ...")
    records = assign_splits(records, cfg.data)
    verify_identity_disjoint(records)  # belt and braces; assign_splits also checks
    print(split_report(records))

    path = write_manifest(records, _manifest_path(cfg))
    print(f"\nVerified identity-disjoint. Wrote {len(records):,} rows to {path}")
    return 0


def cmd_extract(cfg: Config, args: argparse.Namespace) -> int:
    path = _manifest_path(cfg)
    if not path.exists():
        print(
            f"No manifest at {path}. Run `python -m falsora_ai.data manifest` first.",
            file=sys.stderr,
        )
        return 1

    records = read_manifest(path)
    if args.split:
        records = [r for r in records if r.split in args.split]
        print(f"Restricted to splits {args.split}: {len(records):,} videos")
    if args.limit:
        records = stratified_sample(records, args.limit, seed=cfg.data.seed)
        strata = Counter((r.domain, r.label) for r in records)
        detail = "  ".join(f"{d}/{lab}={c}" for (d, lab), c in sorted(strata.items()))
        print(f"Smoke test on {len(records):,} videos — {detail}")

    cfg.paths.ensure()
    results = extract_all(records, cfg, resume=not args.no_resume)

    print()
    print(extraction_report(records, results))
    index = write_crop_index(records, results, cfg.paths.manifests / CROP_INDEX_NAME)
    print(f"\nCrop index: {index}")
    return 0


def cmd_doctor(cfg: Config, args: argparse.Namespace) -> int:
    """Check the environment before committing hours to an extraction run.

    Every dependency here fails at a different moment: pydantic at import,
    OpenCV on the first decode, torch and facenet-pytorch only when the
    detector is first constructed — which is after the run has started. This
    surfaces all of them in a couple of seconds.
    """
    import platform

    print(f"python      {platform.python_version()}  ({sys.executable})")

    ok = True

    def check(label: str, fn) -> None:
        nonlocal ok
        try:
            print(f"{label:<12}{fn()}")
        except Exception as exc:  # noqa: BLE001 — reporting, not handling
            ok = False
            print(f"{label:<12}MISSING — {type(exc).__name__}: {exc}")

    def _pydantic() -> str:
        import pydantic

        if pydantic.VERSION.split(".")[0] != "2":
            raise RuntimeError(f"{pydantic.VERSION} — need 2.x (wrong environment active?)")
        return pydantic.VERSION

    def _numpy() -> str:
        import numpy

        return numpy.__version__

    def _cv2() -> str:
        import cv2

        return cv2.__version__

    def _torch() -> str:
        import torch

        return f"{torch.__version__}  (mps={torch.backends.mps.is_available()}, cuda={torch.cuda.is_available()})"

    def _facenet() -> str:
        import facenet_pytorch

        return getattr(facenet_pytorch, "__version__", "installed")

    check("pydantic", _pydantic)
    check("numpy", _numpy)
    check("opencv", _cv2)
    check("torch", _torch)
    check("facenet", _facenet)

    # torch and numpy are compiled against each other. A torch built for numpy
    # 1.x raises at the first array conversion under numpy 2.x — deep inside
    # MTCNN, long after extraction has started.
    try:
        import numpy as np
        import torch
    except ImportError:
        print("interop     skipped (torch not installed)")
    else:
        try:
            torch.from_numpy(np.zeros((2, 2), dtype=np.float32)).numpy()
            print("interop     torch<->numpy OK")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"interop     BROKEN — {type(exc).__name__}: {exc}")
            print("            torch and numpy were compiled against different major")
            print(f"            versions (torch {torch.__version__}, numpy {np.__version__}).")
            print("            Fix with:  pip install 'numpy<2'")

    print()
    print(f"raw_datasets  {cfg.paths.raw_datasets}  {'found' if cfg.paths.raw_datasets.is_dir() else 'MISSING'}")
    manifest = _manifest_path(cfg)
    print(f"manifest      {manifest}  {'found' if manifest.exists() else 'not built yet'}")

    print()
    print("READY — safe to run extract" if ok else "NOT READY — fix the items above first")
    return 0 if ok else 1


def cmd_report(cfg: Config, args: argparse.Namespace) -> int:
    path = _manifest_path(cfg)
    if not path.exists():
        print(f"No manifest at {path}.", file=sys.stderr)
        return 1
    records = read_manifest(path)
    print(summarise(records))
    print()
    print(split_report(records))

    ledger = cfg.paths.face_crops / LEDGER_NAME
    if ledger.exists():
        print()
        print(extraction_report(records, load_ledger(ledger)))
    else:
        print(f"\nNo extraction ledger yet at {ledger}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m falsora_ai.data",
        description="Falsora AI engine — dataset pipeline (module M1).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("manifest", help="scan datasets, assign splits, write the manifest")

    extract = sub.add_parser("extract", help="extract face crops (slow, resumable)")
    extract.add_argument(
        "--split",
        nargs="+",
        choices=["train", "val", "test", "heldout"],
        help="restrict to these splits (default: all)",
    )
    extract.add_argument(
        "--limit",
        type=int,
        help="smoke-test on N videos sampled evenly across every domain and "
        "label (deterministic, seeded)",
    )
    extract.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore the ledger and re-extract everything",
    )

    sub.add_parser("report", help="summarise the manifest and extraction progress")
    sub.add_parser("doctor", help="check the environment before a long extraction run")

    args = parser.parse_args(argv)
    cfg = Config()

    handlers = {
        "manifest": cmd_manifest,
        "extract": cmd_extract,
        "report": cmd_report,
        "doctor": cmd_doctor,
    }
    return handlers[args.command](cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
