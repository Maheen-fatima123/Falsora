"""Tests for source-image-disjoint splitting of the CASIA v2.0 manifest.

Mirrors ``tests/test_splits.py``'s structure and its central discipline: it is
not enough to show the splitter produces disjoint splits on easy data —
:class:`TestLeakageDetection` deliberately constructs leaked splits and checks
they are rejected, so a future weakening of ``verify_source_disjoint`` goes
red even though every honest split still passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from falsora_ai.config import Config, TamperingConfig
from falsora_ai.data.casia_manifest import ImageRecord, build_casia_manifest
from falsora_ai.data.casia_splits import (
    assign_casia_groups,
    assign_casia_splits,
    casia_split_report,
    verify_source_disjoint,
)
from falsora_ai.data.splits import SPLIT_NAMES, SplitError

CASIA_ROOT = Config().paths.casia_root
needs_casia = pytest.mark.skipif(
    not CASIA_ROOT.is_dir(), reason="raw_datasets/CASIA2 not present (1.2 GB, gitignored)"
)


def make_record(
    relpath: str,
    sources: tuple[str, ...],
    *,
    label: str = "tampered",
    group: str = "",
    split: str = "",
) -> ImageRecord:
    return ImageRecord(relpath=relpath, label=label, sources=sources, group=group, split=split)


def synthetic_casia(n_pairs: int = 200) -> list[ImageRecord]:
    """A miniature CASIA v2.0: ``n_pairs`` disjoint source-id pairs, each with
    two authentic images and one tampered image splicing them together."""
    records: list[ImageRecord] = []
    for i in range(n_pairs):
        a, b = f"casia:a{2 * i}", f"casia:a{2 * i + 1}"
        for source in (a, b):
            records.append(make_record(f"Au/{source}.jpg", (source,), label="authentic"))
        records.append(make_record(f"Tp/{i}.tif", (a, b), label="tampered"))
    return records


# --------------------------------------------------------------------------


class TestGrouping:
    def test_spliced_sources_share_a_group(self) -> None:
        records = assign_casia_groups(
            [
                make_record("Au/a.jpg", ("casia:ani18",), label="authentic"),
                make_record("Au/b.jpg", ("casia:sec96",), label="authentic"),
                make_record("Tp/c.tif", ("casia:ani18", "casia:sec96")),
            ]
        )
        assert len({r.group for r in records}) == 1

    def test_group_id_is_the_smallest_source(self) -> None:
        records = assign_casia_groups([make_record("Tp/c.tif", ("casia:z9", "casia:a2"))])
        assert records[0].group == "casia:a2"

    def test_transitive_chain_forms_one_group(self) -> None:
        """A source appearing across two different Tp images unions all three
        source ids into one group, even though no single image contains all
        three."""
        records = assign_casia_groups(
            [
                make_record("Tp/x.tif", ("casia:a", "casia:b")),
                make_record("Tp/y.tif", ("casia:b", "casia:c")),
            ]
        )
        assert len({r.group for r in records}) == 1

    def test_unrelated_sources_stay_separate(self) -> None:
        records = assign_casia_groups(
            [
                make_record("Tp/x.tif", ("casia:a", "casia:b")),
                make_record("Tp/y.tif", ("casia:m", "casia:n")),
            ]
        )
        assert len({r.group for r in records}) == 2

    def test_record_without_sources_is_rejected(self) -> None:
        with pytest.raises(SplitError, match="no sources"):
            assign_casia_groups([make_record("Au/x.jpg", ())])

    def test_copy_move_duplicate_source_does_not_break_grouping(self) -> None:
        """A copy-move Tp image carries the same source twice — union(a, a)
        must be a harmless no-op, not an error."""
        records = assign_casia_groups(
            [make_record("Tp/x.tif", ("casia:a11", "casia:a11"))]
        )
        assert records[0].group == "casia:a11"


class TestLeakageDetection:
    """Negative tests. These prove the verifier is not vacuous."""

    def test_source_in_two_splits_is_rejected(self) -> None:
        leaked = [
            make_record("Au/a.jpg", ("casia:x",), label="authentic", split="train"),
            make_record("Tp/b.tif", ("casia:x", "casia:y"), split="test"),
        ]
        with pytest.raises(SplitError, match="SOURCE LEAKAGE"):
            verify_source_disjoint(leaked)

    def test_leakage_via_the_second_source_is_caught(self) -> None:
        leaked = [
            make_record("Tp/a.tif", ("casia:x", "casia:y"), split="train"),
            make_record("Tp/b.tif", ("casia:z", "casia:y"), split="test"),
        ]
        with pytest.raises(SplitError, match="SOURCE LEAKAGE"):
            verify_source_disjoint(leaked)

    def test_unassigned_record_is_rejected(self) -> None:
        with pytest.raises(SplitError, match="no split"):
            verify_source_disjoint([make_record("Au/a.jpg", ("casia:x",), label="authentic")])

    def test_same_source_within_one_split_is_fine(self) -> None:
        ok = [
            make_record("Au/a.jpg", ("casia:x",), label="authentic", split="train"),
            make_record("Tp/b.tif", ("casia:x", "casia:y"), split="train"),
        ]
        verify_source_disjoint(ok)  # must not raise


class TestAssignSplits:
    def test_result_is_source_disjoint(self) -> None:
        verify_source_disjoint(assign_casia_splits(synthetic_casia()))

    def test_every_record_is_assigned(self) -> None:
        records = assign_casia_splits(synthetic_casia())
        assert all(r.split in SPLIT_NAMES for r in records)

    def test_a_group_is_never_divided(self) -> None:
        records = assign_casia_splits(synthetic_casia())
        by_group: dict[str, set[str]] = {}
        for rec in records:
            by_group.setdefault(rec.group, set()).add(rec.split)
        assert all(len(s) == 1 for s in by_group.values())

    def test_ratios_are_close_to_target(self) -> None:
        cfg = TamperingConfig()
        records = assign_casia_splits(synthetic_casia(500), cfg)
        total = len(records)
        for name, target in [
            ("train", cfg.train_ratio),
            ("val", cfg.val_ratio),
            ("test", cfg.test_ratio),
        ]:
            got = sum(1 for r in records if r.split == name) / total
            assert abs(got - target) < 0.02, f"{name}: {got:.3f} vs target {target}"

    def test_is_deterministic(self) -> None:
        first = {r.relpath: r.split for r in assign_casia_splits(synthetic_casia())}
        second = {r.relpath: r.split for r in assign_casia_splits(synthetic_casia())}
        assert first == second

    def test_seed_actually_changes_the_split(self) -> None:
        base = assign_casia_splits(synthetic_casia(), TamperingConfig())
        other = assign_casia_splits(synthetic_casia(), TamperingConfig(split_seed=99))
        assert {r.relpath: r.split for r in base} != {r.relpath: r.split for r in other}

    def test_accepts_pre_grouped_records(self) -> None:
        grouped = assign_casia_groups(synthetic_casia(20))
        assert all(r.split for r in assign_casia_splits(grouped))

    def test_authentic_and_tampered_both_reach_training(self) -> None:
        records = assign_casia_splits(synthetic_casia(100))
        labels = {r.label for r in records if r.split == "train"}
        assert labels == {"authentic", "tampered"}


@needs_casia
class TestAgainstRealDataset:
    """Checked on the actual 12,614 CASIA v2.0 files. Skipped in CI."""

    @pytest.fixture(scope="class")
    def records(self) -> list[ImageRecord]:
        cfg = TamperingConfig()
        return assign_casia_splits(build_casia_manifest(CASIA_ROOT, cfg), cfg)

    def test_no_source_leakage(self, records: list[ImageRecord]) -> None:
        verify_source_disjoint(records)

    def test_every_split_contains_both_labels(self, records: list[ImageRecord]) -> None:
        for split in SPLIT_NAMES:
            labels = {r.label for r in records if r.split == split}
            assert labels == {"authentic", "tampered"}, f"{split} has labels {labels}"

    def test_manifest_round_trips_after_splitting(
        self, records: list[ImageRecord], tmp_path: Path
    ) -> None:
        from falsora_ai.data.casia_manifest import read_casia_manifest, write_casia_manifest

        path = write_casia_manifest(records, tmp_path / "casia.csv")
        loaded = read_casia_manifest(path)
        assert sorted(loaded, key=lambda r: r.relpath) == sorted(records, key=lambda r: r.relpath)


def test_split_report_runs_without_error() -> None:
    report = casia_split_report(assign_casia_splits(synthetic_casia(20)))
    assert "train" in report and "test" in report
