"""
Source-image-disjoint train / val / test splits for CASIA v2.0.
=================================================================

Same failure mode as :mod:`falsora_ai.data.splits`, different unit. There,
splitting by video leaks a face; here, splitting by image leaks a **source
image's content** — ``Au_ani_00018.jpg`` and every ``Tp`` image spliced or
copy-moved from it must land in the same split, or the tampering classifier
can learn that one image's texture instead of what tampering looks like in
general.

The algorithm is the video-split algorithm minus the per-domain loop, because
CASIA v2.0 is one domain — but *with* a stratification step of its own:

1. **Union-find over source ids.** A ``Tp`` image with two different sources
   unions them into one component — the indivisible unit of splitting.
2. **Greedy packing per label stratum, weighted by image count, largest
   components first.** See "A note on CASIA v2.0" below for why this is not
   the single global pack ``splits.py`` uses within a domain.
3. **Verification, not trust.** :func:`verify_source_disjoint` re-derives the
   source→split mapping from scratch and raises on any overlap, exactly as
   ``verify_identity_disjoint`` does for identities.

A note on CASIA v2.0
---------------------
CASIA v2.0's source images are reused promiscuously — the same authentic
photo spliced into dozens of different Tp images — so the union-find above
does not stay small. On the real dataset it produces one component of 3,813
records holding 3,019 of the 5,123 tampered images (59%), plus ~980 much
smaller tampered-linked components, and ~5,500 singleton authentic-only
components.

A single global pack (the DFD strategy in ``splits.py``, "roughly right
ratios, one big block wherever it lands") is not good enough here: sorted
largest-first, that one 3,813-record component and the ~980 components behind
it are exactly big enough to exhaust train's *entire* quota deficit before the
packer ever reaches a val or test slot — leaving val and test 100% authentic,
0% tampered, which makes AUC on either undefined. This was caught by
``TestAgainstRealDataset.test_every_split_contains_both_labels`` on the real
12,614-image dataset (the synthetic test fixture is too small and too evenly
shaped to reproduce it).

The fix is to pack tampered-linked components and authentic-only components as
two separate pools, each against the same 72/14/14 targets, then merge. This
guarantees every split gets its proportional share of *both* labels
independently, rather than leaving that to arithmetic that happens to work out
for videos but does not for this dataset's skewed component sizes.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import replace

from falsora_ai.config import TamperingConfig
from falsora_ai.data.casia_manifest import ImageRecord
from falsora_ai.data.splits import SPLIT_NAMES, SplitError, UnionFind

__all__ = [
    "assign_casia_groups",
    "assign_casia_splits",
    "verify_source_disjoint",
    "casia_split_report",
]


def assign_casia_groups(records: list[ImageRecord]) -> list[ImageRecord]:
    """Return records with ``group`` set to their source-image component.

    The group id is the lexicographically smallest source id in the
    component, for the same readability reason as ``assign_groups`` in the
    video pipeline.

    Raises:
        SplitError: If a record has no sources — it cannot be split safely.
    """
    uf = UnionFind()
    for rec in records:
        if not rec.sources:
            raise SplitError(f"{rec.relpath} has no sources; cannot be split safely")
        first = rec.sources[0]
        uf.add(first)
        for other in rec.sources[1:]:
            uf.union(first, other)

    group_id = {root: min(members) for root, members in uf.components().items()}
    return [replace(rec, group=group_id[uf.find(rec.sources[0])]) for rec in records]


def _pack(weights: dict[str, int], targets: dict[str, float], seed: int) -> dict[str, str]:
    """Assign each group to a split, greedily filling the largest deficit.

    Same strategy as ``falsora_ai.data.splits._pack``, kept as its own copy
    rather than imported: that function is private to the video-split module,
    and CASIA has no per-domain loop around this call — reusing it would mean
    exporting an implementation detail across modules for a few lines.
    """
    active = [s for s in SPLIT_NAMES if targets.get(s, 0.0) > 0.0]
    if not active:
        raise SplitError(f"No split has a positive target: {targets}")

    scale = sum(targets[s] for s in active)
    total = sum(weights.values())
    quota = {s: targets[s] / scale * total for s in active}
    filled = dict.fromkeys(active, 0.0)

    groups = list(weights)
    random.Random(seed).shuffle(groups)  # break weight ties without positional bias
    groups.sort(key=lambda g: weights[g], reverse=True)  # stable: keeps shuffle order

    assignment: dict[str, str] = {}
    for group in groups:
        best = max(active, key=lambda s: (quota[s] - filled[s], -active.index(s)))
        assignment[group] = best
        filled[best] += weights[group]
    return assignment


def assign_casia_splits(
    records: list[ImageRecord], cfg: TamperingConfig | None = None
) -> list[ImageRecord]:
    """Assign ``train`` / ``val`` / ``test`` to every image, source-disjoint.

    Grouping is performed first if it has not been already, so callers can
    simply pipe ``build_casia_manifest`` into this function.

    Packs tampered-linked and authentic-only components as two separate pools
    against the same targets, then merges — see "A note on CASIA v2.0" in the
    module docstring for why a single global pack leaves val/test with no
    tampered images at all on the real dataset.
    """
    cfg = cfg or TamperingConfig()
    if any(not rec.group for rec in records):
        records = assign_casia_groups(records)

    by_group: dict[str, list[ImageRecord]] = defaultdict(list)
    for rec in records:
        by_group[rec.group].append(rec)

    targets = {"train": cfg.train_ratio, "val": cfg.val_ratio, "test": cfg.test_ratio}
    assignment: dict[str, str] = {}
    for stratum, seed_offset in (("tampered", 0), ("authentic", 1)):
        pool = {
            group: recs
            for group, recs in by_group.items()
            if any(r.label == "tampered" for r in recs) == (stratum == "tampered")
        }
        if not pool:
            continue
        weights = {group: len(recs) for group, recs in pool.items()}
        assignment.update(_pack(weights, targets, cfg.split_seed + seed_offset))

    out = [replace(rec, split=assignment[rec.group]) for rec in records]
    verify_source_disjoint(out)
    return out


def verify_source_disjoint(records: list[ImageRecord]) -> None:
    """Re-derive source→split from scratch and raise on any overlap.

    Raises:
        SplitError: On any source id appearing in more than one split, or any
            record left unassigned.
    """
    unassigned = [r.relpath for r in records if not r.split]
    if unassigned:
        raise SplitError(f"{len(unassigned)} records have no split, e.g. {unassigned[:3]}")

    splits_of: dict[str, set[str]] = defaultdict(set)
    for rec in records:
        for source in rec.sources:
            splits_of[source].add(rec.split)

    leaked = {s: sorted(v) for s, v in splits_of.items() if len(v) > 1}
    if leaked:
        sample = dict(list(leaked.items())[:5])
        raise SplitError(
            f"SOURCE LEAKAGE: {len(leaked)} source images appear in more than one "
            f"split, e.g. {sample}. Every metric computed from this split would "
            "be inflated. Do not proceed."
        )


def casia_split_report(records: list[ImageRecord]) -> str:
    """Realised split composition — printed by the CLI."""
    by: dict[tuple[str, str], list[ImageRecord]] = defaultdict(list)
    for rec in records:
        by[(rec.split, rec.label)].append(rec)

    order = {name: i for i, name in enumerate(SPLIT_NAMES)}
    lines = [f"{'split':<8}{'label':<12}{'images':>8}{'groups':>8}", "-" * 36]
    for key in sorted(by, key=lambda k: (order.get(k[0], 9), k[1])):
        split, label = key
        group = by[key]
        lines.append(
            f"{split:<8}{label:<12}{len(group):>8}{len({r.group for r in group}):>8}"
        )
    return "\n".join(lines)
