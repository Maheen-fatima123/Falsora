"""
Identity-disjoint train / val / test splits.
============================================

This is the highest-risk code in the project. Everything else can be wrong and
produce an obviously bad number; this can be wrong and produce a beautiful one.

The failure mode
----------------
Split face crops randomly and the same person appears in train and test. The
model memorises faces, test accuracy reaches 99%, and the system collapses to
65–75% on anyone it has not met. Published deepfake results have been retracted
over exactly this. So the unit of splitting here is never a frame and never
even a video — it is a **connected component of human identities**.

The algorithm
-------------
1. **Union-find over identities.** Every video contributes an edge between the
   people appearing in it (``000_003.mp4`` links identity 000 to identity 003).
   The connected components are the atoms: indivisible, because splitting one
   would put a person on both sides.

2. **Greedy packing per domain, weighted by crop count.** Components are
   shuffled with a fixed seed, sorted largest-first, and each is assigned to
   whichever split is furthest below its quota. Largest-first matters: placing
   big components while there is still slack everywhere is what keeps the final
   ratios close to target.

   Splitting *per domain* rather than globally guarantees every domain is
   represented in train, instead of leaving that to the packer's arithmetic.

   The weight is expected face crops, not video count, because crops are what
   the model actually sees. A REAL video contributing 32 crops should not be
   packed as though it were interchangeable with a FAKE contributing 7.

3. **Verification, not trust.** :func:`verify_identity_disjoint` re-derives the
   identity→split mapping from scratch and raises on any overlap. It runs in
   the CLI and in the test suite. The algorithm above is *believed* correct; the
   check is what makes it *known* correct.

Held-out domains are never split. Every one of their videos is test data by
definition and is marked ``heldout``.

A note on DFD
-------------
FF++ partitions beautifully: 500 components of exactly 2 identities, giving
360/70/70 at our ratios. DFD does not. Its 28 actors collapse into just 3
components (18, 5 and 5 actors), because the actor-pairing graph is dense — so
83% of DFD is a single indivisible block. The packer therefore produces roughly
1005/110/85 videos rather than a clean 72/14/14, and the DFD val and test sets
are small enough that a standalone AUC on them carries a wide confidence
interval. That is a property of the dataset, not a bug, and the fix is to report
the sample size alongside the metric — never to break a component apart to make
the percentages look tidier.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import replace

from falsora_ai.config import DataConfig
from falsora_ai.data.manifest import VideoRecord

__all__ = [
    "SplitError",
    "UnionFind",
    "assign_groups",
    "assign_splits",
    "verify_identity_disjoint",
    "split_report",
    "SPLIT_NAMES",
    "HELDOUT_SPLIT",
]

SPLIT_NAMES = ("train", "val", "test")
HELDOUT_SPLIT = "heldout"


class SplitError(RuntimeError):
    """A split invariant was violated. Never recoverable — always a stop."""


# --------------------------------------------------------------------------
# Union-find
# --------------------------------------------------------------------------


class UnionFind:
    """Disjoint-set with path compression and union by size.

    Deliberately tiny and dependency-free. Kept as an explicit class rather than
    inlined so it can be tested directly against hand-built cases.
    """

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._size: dict[str, int] = {}

    def add(self, item: str) -> None:
        if item not in self._parent:
            self._parent[item] = item
            self._size[item] = 1

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:  # path compression
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._size[ra] < self._size[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size[rb]

    def components(self) -> dict[str, set[str]]:
        """Map canonical root → members. Roots are internal; use group ids."""
        out: dict[str, set[str]] = defaultdict(set)
        for item in self._parent:
            out[self.find(item)].add(item)
        return dict(out)


# --------------------------------------------------------------------------
# Grouping
# --------------------------------------------------------------------------


def assign_groups(records: list[VideoRecord]) -> list[VideoRecord]:
    """Return records with ``group`` set to their identity component.

    The group id is the lexicographically smallest identity in the component,
    which makes the manifest readable: a reviewer can see at a glance that
    ``ffpp:000`` and ``ffpp:003`` are one group.

    Raises:
        SplitError: If a component spans domains. Identity keys are namespaced
            precisely to prevent that, so it would mean a parser is emitting a
            key with the wrong prefix — which would silently defeat per-domain
            splitting.
    """
    uf = UnionFind()
    for rec in records:
        if not rec.identities:
            raise SplitError(f"{rec.relpath} has no identities; cannot be split safely")
        first = rec.identities[0]
        uf.add(first)
        for other in rec.identities[1:]:
            uf.union(first, other)

    # Canonical, human-readable group id per component.
    group_id = {
        root: min(members) for root, members in uf.components().items()
    }

    # A component must not mix domains, or "split domain by domain" is a lie.
    domains_in_group: dict[str, set[str]] = defaultdict(set)
    for rec in records:
        domains_in_group[group_id[uf.find(rec.identities[0])]].add(rec.domain)
    mixed = {g: d for g, d in domains_in_group.items() if len(d) > 1}
    if mixed:
        raise SplitError(f"Identity components span multiple domains: {mixed}")

    return [
        replace(rec, group=group_id[uf.find(rec.identities[0])]) for rec in records
    ]


# --------------------------------------------------------------------------
# Packing
# --------------------------------------------------------------------------


def _pack(
    weights: dict[str, int], targets: dict[str, float], seed: int
) -> dict[str, str]:
    """Assign each group to a split, greedily filling the largest deficit.

    Args:
        weights: group id → expected crop count.
        targets: split name → fraction of total.
        seed: fixes the shuffle, so the same manifest always yields the same
            split. Reproducibility is not a nicety here — a split that changes
            between runs makes every reported metric unreproducible.

    Returns:
        group id → split name.
    """
    # Splits given a zero target are not candidates at all. Leaving them in
    # would let them win once every other split is over-quota and deficits have
    # gone negative — silently reintroducing the tiny validation set the caller
    # asked to avoid.
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
        # Largest remaining deficit wins; SPLIT_NAMES order breaks exact ties.
        best = max(active, key=lambda s: (quota[s] - filled[s], -active.index(s)))
        assignment[group] = best
        filled[best] += weights[group]
    return assignment


def assign_splits(
    records: list[VideoRecord], data: DataConfig | None = None
) -> list[VideoRecord]:
    """Assign ``train`` / ``val`` / ``test`` to the train pool, ``heldout`` to the rest.

    Grouping is performed first if it has not been already, so callers can
    simply pipe ``build_manifest`` into this function.
    """
    data = data or DataConfig()
    if any(not rec.group for rec in records):
        records = assign_groups(records)

    assignment: dict[str, str] = {}
    by_domain: dict[str, list[VideoRecord]] = defaultdict(list)
    for rec in records:
        by_domain[rec.domain].append(rec)

    for domain, domain_records in sorted(by_domain.items()):
        if data.DOMAIN_ROLES[domain] == "heldout_test":
            for rec in domain_records:
                assignment[rec.group] = HELDOUT_SPLIT
            continue

        weights: dict[str, int] = defaultdict(int)
        for rec in domain_records:
            weights[rec.group] += rec.frames

        # Too few indivisible groups to carve a meaningful validation set out
        # of: fold its share into test so at least one slice is large enough to
        # support a confidence interval. See DataConfig.min_groups_for_val.
        if len(weights) < data.min_groups_for_val:
            targets = {
                "train": data.train_ratio,
                "test": data.val_ratio + data.test_ratio,
            }
        else:
            targets = {
                "train": data.train_ratio,
                "val": data.val_ratio,
                "test": data.test_ratio,
            }
        # Seed varies per domain so the domains are packed independently rather
        # than receiving correlated shuffles.
        domain_seed = data.split_seed + sum(ord(c) for c in domain)
        assignment.update(_pack(dict(weights), targets, domain_seed))

    out = [replace(rec, split=assignment[rec.group]) for rec in records]
    verify_identity_disjoint(out)
    return out


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


def verify_identity_disjoint(records: list[VideoRecord]) -> None:
    """Re-derive identity → splits from scratch and raise on any overlap.

    This does not reuse groups or the union-find. It looks only at the final
    ``split`` values and the raw ``identities``, so it would catch a bug in the
    grouping just as readily as a bug in the packing.

    ``heldout`` counts as a split for this purpose: a Celeb-DF identity must not
    also appear in the training pool. It cannot today, because identity keys are
    namespaced by domain, but that is an invariant worth enforcing rather than
    assuming.

    Raises:
        SplitError: On any identity appearing in more than one split, or any
            record left unassigned.
    """
    unassigned = [r.relpath for r in records if not r.split]
    if unassigned:
        raise SplitError(
            f"{len(unassigned)} records have no split, e.g. {unassigned[:3]}"
        )

    splits_of: dict[str, set[str]] = defaultdict(set)
    for rec in records:
        for identity in rec.identities:
            splits_of[identity].add(rec.split)

    leaked = {i: sorted(s) for i, s in splits_of.items() if len(s) > 1}
    if leaked:
        sample = dict(list(leaked.items())[:5])
        raise SplitError(
            f"IDENTITY LEAKAGE: {len(leaked)} identities appear in more than one "
            f"split, e.g. {sample}. Every metric computed from this split would "
            "be inflated. Do not proceed."
        )


def split_report(records: list[VideoRecord]) -> str:
    """Realised split composition — printed by the CLI, pasted into the report."""
    by: dict[tuple[str, str, str], list[VideoRecord]] = defaultdict(list)
    for rec in records:
        by[(rec.domain, rec.split, rec.label)].append(rec)

    order = {name: i for i, name in enumerate((*SPLIT_NAMES, HELDOUT_SPLIT))}
    lines = [
        f"{'domain':<10}{'split':<10}{'label':<7}{'videos':>8}{'crops':>10}{'groups':>8}",
        "-" * 53,
    ]
    for key in sorted(by, key=lambda k: (k[0], order.get(k[1], 9), k[2])):
        domain, split, label = key
        group = by[key]
        lines.append(
            f"{domain:<10}{split:<10}{label:<7}{len(group):>8}"
            f"{sum(r.frames for r in group):>10,}"
            f"{len({r.group for r in group}):>8}"
        )

    lines.append("-" * 53)
    train = [r for r in records if r.split == "train"]
    real = sum(r.frames for r in train if r.label == "real")
    fake = sum(r.frames for r in train if r.label == "fake")
    if real:
        lines.append(f"TRAIN balance: real={real:,} fake={fake:,} → {fake / real:.2f}:1 fake:real")
    return "\n".join(lines)
