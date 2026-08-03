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
import sys
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
    build_manifest,
    read_manifest,
    summarise,
    write_manifest,
)
from falsora_ai.data.splits import assign_splits, split_report, verify_identity_disjoint

MANIFEST_NAME = "videos.csv"


def _manifest_path(cfg: Config) -> Path:
    return cfg.paths.manifests / MANIFEST_NAME


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
        records = records[: args.limit]
        print(f"Limited to the first {len(records):,} videos (smoke test)")

    cfg.paths.ensure()
    results = extract_all(records, cfg, resume=not args.no_resume)

    print()
    print(extraction_report(records, results))
    index = write_crop_index(records, results, cfg.paths.manifests / CROP_INDEX_NAME)
    print(f"\nCrop index: {index}")
    return 0


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
        "--limit", type=int, help="stop after N videos — use this to smoke-test first"
    )
    extract.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore the ledger and re-extract everything",
    )

    sub.add_parser("report", help="summarise the manifest and extraction progress")

    args = parser.parse_args(argv)
    cfg = Config()

    handlers = {
        "manifest": cmd_manifest,
        "extract": cmd_extract,
        "report": cmd_report,
    }
    return handlers[args.command](cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
