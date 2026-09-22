"""
Dataset pipeline: manifest, identity-disjoint splits, face crop extraction.
===========================================================================

Nothing here imports torch. The manifest and split logic run in a plain
``[dev]`` environment so CI can verify the leakage guarantees without a GPU or a
2 GB download; only :mod:`falsora_ai.data.extract` needs OpenCV, and only its
default detector needs torch — imported lazily, at call time.

Typical use::

    from falsora_ai.config import Config
    from falsora_ai.data import build_manifest, assign_splits

    cfg = Config()
    records = assign_splits(build_manifest(cfg.paths.raw_datasets, cfg.data), cfg.data)

or from the command line::

    python -m falsora_ai.data manifest
    python -m falsora_ai.data extract
"""

from falsora_ai.data.identity import IdentityParseError, identities_for
from falsora_ai.data.manifest import (
    MANIFEST_VERSION,
    VideoRecord,
    build_manifest,
    read_manifest,
    summarise,
    write_manifest,
)
from falsora_ai.data.splits import (
    HELDOUT_SPLIT,
    SPLIT_NAMES,
    SplitError,
    assign_groups,
    assign_splits,
    split_report,
    verify_identity_disjoint,
)

__all__ = [
    "HELDOUT_SPLIT",
    "MANIFEST_VERSION",
    "SPLIT_NAMES",
    "IdentityParseError",
    "SplitError",
    "VideoRecord",
    "assign_groups",
    "assign_splits",
    "build_manifest",
    "identities_for",
    "read_manifest",
    "split_report",
    "summarise",
    "verify_identity_disjoint",
    "write_manifest",
]
