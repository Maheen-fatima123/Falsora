"""Tests for identity-disjoint splitting.

The suite is built around one idea: it is not enough to check that the splitter
produces disjoint splits on data that happens to be easy. It must be shown that
the *detector* fires on data that is not — otherwise a green suite proves only
that the verifier is asleep.

So :class:`TestLeakageDetection` deliberately constructs leaked splits and
asserts they are rejected. If someone later weakens
``verify_identity_disjoint``, those tests go red even though every honest split
still passes.

Everything here runs on synthetic manifests. ``raw_datasets/`` is 26 GB and
gitignored, so CI never sees it; the real-data checks live in
:class:`TestAgainstRealDatasets` and skip cleanly when the data is absent.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from falsora_ai.config import Config, DataConfig
from falsora_ai.data.manifest import VideoRecord
from falsora_ai.data.splits import (
    HELDOUT_SPLIT,
    SPLIT_NAMES,
    SplitError,
    UnionFind,
    assign_groups,
    assign_splits,
    verify_identity_disjoint,
)

RAW = Config().paths.raw_datasets
needs_datasets = pytest.mark.skipif(
    not RAW.is_dir(), reason="raw_datasets/ not present (26 GB, gitignored)"
)


def make_record(
    relpath: str,
    identities: tuple[str, ...],
    *,
    domain: str = "ffpp",
    label: str = "fake",
    role: str = "train_pool",
    frames: int = 7,
    group: str = "",
    split: str = "",
) -> VideoRecord:
    return VideoRecord(
        relpath=relpath,
        source="FaceForensics++_C23/Deepfakes",
        domain=domain,
        label=label,
        role=role,
        identities=identities,
        frames=frames,
        group=group,
        split=split,
    )


def synthetic_ffpp(n_pairs: int = 200) -> list[VideoRecord]:
    """A miniature FF++: ``n_pairs`` disjoint identity pairs, each with one real
    original per identity and one manipulation linking them."""
    records: list[VideoRecord] = []
    for i in range(n_pairs):
        a, b = f"ffpp:{2 * i:03d}", f"ffpp:{2 * i + 1:03d}"
        for ident in (a, b):
            records.append(
                make_record(
                    f"orig/{ident}.mp4", (ident,), label="real", frames=32
                )
            )
        records.append(make_record(f"fake/{i}.mp4", (a, b), label="fake", frames=7))
    return records


# --------------------------------------------------------------------------


class TestUnionFind:
    def test_isolated_items_are_their_own_components(self) -> None:
        uf = UnionFind()
        for x in "abc":
            uf.add(x)
        assert len(uf.components()) == 3

    def test_union_is_transitive(self) -> None:
        uf = UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        assert uf.find("a") == uf.find("c")
        assert len(uf.components()) == 1

    def test_union_is_symmetric(self) -> None:
        left, right = UnionFind(), UnionFind()
        left.union("a", "b")
        right.union("b", "a")
        assert (len(left.components()) == len(right.components()) == 1)

    def test_repeated_union_is_idempotent(self) -> None:
        uf = UnionFind()
        for _ in range(5):
            uf.union("a", "b")
        assert len(uf.components()) == 1

    def test_chain_collapses_to_one_component(self) -> None:
        """Path compression must not lose members."""
        uf = UnionFind()
        for i in range(500):
            uf.union(f"n{i}", f"n{i + 1}")
        comps = uf.components()
        assert len(comps) == 1
        assert len(next(iter(comps.values()))) == 501


class TestGrouping:
    def test_paired_identities_share_a_group(self) -> None:
        records = assign_groups(
            [
                make_record("a.mp4", ("ffpp:000",), label="real"),
                make_record("b.mp4", ("ffpp:003",), label="real"),
                make_record("c.mp4", ("ffpp:000", "ffpp:003")),
            ]
        )
        assert len({r.group for r in records}) == 1

    def test_group_id_is_the_smallest_identity(self) -> None:
        """Readable group ids make the manifest reviewable in a pull request."""
        records = assign_groups([make_record("c.mp4", ("ffpp:009", "ffpp:002"))])
        assert records[0].group == "ffpp:002"

    def test_transitive_chain_forms_one_group(self) -> None:
        """``000_003`` and ``003_007`` put all three people in one group, even
        though no single video contains 000 and 007 together."""
        records = assign_groups(
            [
                make_record("x.mp4", ("ffpp:000", "ffpp:003")),
                make_record("y.mp4", ("ffpp:003", "ffpp:007")),
            ]
        )
        assert len({r.group for r in records}) == 1

    def test_unrelated_identities_stay_separate(self) -> None:
        records = assign_groups(
            [
                make_record("x.mp4", ("ffpp:000", "ffpp:003")),
                make_record("y.mp4", ("ffpp:100", "ffpp:107")),
            ]
        )
        assert len({r.group for r in records}) == 2

    def test_record_without_identities_is_rejected(self) -> None:
        with pytest.raises(SplitError, match="no identities"):
            assign_groups([make_record("x.mp4", ())])

    def test_component_spanning_domains_is_rejected(self) -> None:
        """Namespacing should make this impossible; the check exists so that a
        parser emitting a wrong prefix fails loudly instead of quietly
        defeating per-domain splitting."""
        records = [
            make_record("x.mp4", ("ffpp:000", "shared:1"), domain="ffpp"),
            make_record("y.mp4", ("shared:1", "dfd:01"), domain="dfd"),
        ]
        with pytest.raises(SplitError, match="span multiple domains"):
            assign_groups(records)


class TestLeakageDetection:
    """Negative tests. These prove the verifier is not vacuous."""

    def test_identity_in_two_splits_is_rejected(self) -> None:
        leaked = [
            make_record("a.mp4", ("ffpp:000",), split="train"),
            make_record("b.mp4", ("ffpp:000",), split="test"),
        ]
        with pytest.raises(SplitError, match="IDENTITY LEAKAGE"):
            verify_identity_disjoint(leaked)

    def test_leakage_via_the_second_identity_is_caught(self) -> None:
        """The subtle case: the target ids differ, and only the *source* face is
        shared. This is precisely the bug the whole module exists to prevent."""
        leaked = [
            make_record("a.mp4", ("ffpp:000", "ffpp:003"), split="train"),
            make_record("b.mp4", ("ffpp:100", "ffpp:003"), split="test"),
        ]
        with pytest.raises(SplitError, match="IDENTITY LEAKAGE"):
            verify_identity_disjoint(leaked)

    def test_leakage_between_train_and_heldout_is_caught(self) -> None:
        leaked = [
            make_record("a.mp4", ("celebdf:id0",), split="train"),
            make_record("b.mp4", ("celebdf:id0",), split=HELDOUT_SPLIT),
        ]
        with pytest.raises(SplitError, match="IDENTITY LEAKAGE"):
            verify_identity_disjoint(leaked)

    def test_unassigned_record_is_rejected(self) -> None:
        with pytest.raises(SplitError, match="no split"):
            verify_identity_disjoint([make_record("a.mp4", ("ffpp:000",))])

    def test_same_identity_within_one_split_is_fine(self) -> None:
        """Guard against over-eager detection: repetition inside a split is
        normal and must not raise."""
        ok = [
            make_record("a.mp4", ("ffpp:000",), split="train"),
            make_record("b.mp4", ("ffpp:000", "ffpp:003"), split="train"),
        ]
        verify_identity_disjoint(ok)  # must not raise


class TestAssignSplits:
    def test_result_is_identity_disjoint(self) -> None:
        records = assign_splits(synthetic_ffpp())
        verify_identity_disjoint(records)

    def test_every_record_is_assigned(self) -> None:
        records = assign_splits(synthetic_ffpp())
        assert all(r.split in SPLIT_NAMES for r in records)

    def test_a_group_is_never_divided(self) -> None:
        records = assign_splits(synthetic_ffpp())
        by_group: dict[str, set[str]] = {}
        for rec in records:
            by_group.setdefault(rec.group, set()).add(rec.split)
        assert all(len(s) == 1 for s in by_group.values())

    def test_ratios_are_close_to_target(self) -> None:
        data = DataConfig()
        records = assign_splits(synthetic_ffpp(500), data)
        total = sum(r.frames for r in records)
        for name, target in [
            ("train", data.train_ratio),
            ("val", data.val_ratio),
            ("test", data.test_ratio),
        ]:
            got = sum(r.frames for r in records if r.split == name) / total
            assert abs(got - target) < 0.02, f"{name}: {got:.3f} vs target {target}"

    def test_is_deterministic(self) -> None:
        """A split that changes between runs makes every metric unreproducible."""
        first = {r.relpath: r.split for r in assign_splits(synthetic_ffpp())}
        second = {r.relpath: r.split for r in assign_splits(synthetic_ffpp())}
        assert first == second

    def test_seed_actually_changes_the_split(self) -> None:
        """Determinism must come from the seed, not from the algorithm ignoring
        it — otherwise ``split_seed`` is decorative."""
        base = assign_splits(synthetic_ffpp(), DataConfig())
        other = assign_splits(synthetic_ffpp(), DataConfig(split_seed=99))
        assert {r.relpath: r.split for r in base} != {r.relpath: r.split for r in other}

    def test_accepts_pre_grouped_records(self) -> None:
        grouped = assign_groups(synthetic_ffpp(20))
        assert all(r.split for r in assign_splits(grouped))

    def test_heldout_domain_is_never_split(self) -> None:
        records = [
            make_record(
                f"c{i}.mp4",
                (f"celebdf:id{i}",),
                domain="celebdf",
                role="heldout_test",
                frames=32,
            )
            for i in range(50)
        ]
        assert {r.split for r in assign_splits(records)} == {HELDOUT_SPLIT}

    def test_domains_are_split_independently(self) -> None:
        """Every training domain must reach train, rather than one domain being
        pushed entirely into test by the packer's global arithmetic."""
        records = synthetic_ffpp(100) + [
            make_record(f"d{i}.mp4", (f"dfd:{i:02d}",), domain="dfd", frames=7)
            for i in range(30)
        ]
        out = assign_splits(records)
        for domain in ("ffpp", "dfd"):
            splits = {r.split for r in out if r.domain == domain}
            assert "train" in splits, f"{domain} has no training data"


class TestSmallDomainPolicy:
    """A domain with too few indivisible groups gets train/test only.

    DFD is the real case: 28 actors that collapse into 3 components. A three-way
    split leaves 11 real videos in test, which cannot support a meaningful AUC.
    """

    @staticmethod
    def _domain(n_groups: int) -> list[VideoRecord]:
        return [
            make_record(f"d{i}.mp4", (f"dfd:{i:02d}",), domain="dfd", frames=10)
            for i in range(n_groups)
        ]

    def test_too_few_groups_yields_no_validation_set(self) -> None:
        data = DataConfig(min_groups_for_val=10)
        out = assign_splits(self._domain(3), data)
        assert {r.split for r in out} == {"train", "test"}

    def test_enough_groups_yields_all_three(self) -> None:
        data = DataConfig(min_groups_for_val=10)
        out = assign_splits(self._domain(40), data)
        assert {r.split for r in out} == {"train", "val", "test"}

    def test_test_share_absorbs_the_validation_share(self) -> None:
        """The point of the policy: test gets bigger, not the data discarded."""
        data = DataConfig(min_groups_for_val=10)
        out = assign_splits(self._domain(4), data)
        total = sum(r.frames for r in out)
        test = sum(r.frames for r in out if r.split == "test")
        assert test / total >= data.val_ratio + data.test_ratio - 0.15

    def test_small_domain_is_still_identity_disjoint(self) -> None:
        verify_identity_disjoint(assign_splits(self._domain(3), DataConfig()))


@pytest.fixture(scope="module")
def records() -> list[VideoRecord]:
    """Manifest + splits over the real datasets. Built once for the module."""
    from falsora_ai.data.manifest import build_manifest

    cfg = Config()
    return assign_splits(build_manifest(cfg.paths.raw_datasets, cfg.data), cfg.data)


@needs_datasets
class TestAgainstRealDatasets:
    """The properties that matter, checked on the actual 13,729 files.

    Skipped in CI, run locally before any training job.
    """

    def test_no_identity_leakage(self, records: list[VideoRecord]) -> None:
        verify_identity_disjoint(records)

    def test_celebdf_is_entirely_heldout(self, records: list[VideoRecord]) -> None:
        celeb = [r for r in records if r.domain == "celebdf"]
        assert celeb, "Celeb-DF missing from the manifest"
        assert {r.split for r in celeb} == {HELDOUT_SPLIT}

    def test_no_celebdf_identity_appears_in_training(
        self, records: list[VideoRecord]
    ) -> None:
        """The whole reason Celeb-DF is held out."""
        trained = {
            i for r in records if r.split == "train" for i in r.identities
        }
        heldout = {
            i for r in records if r.split == HELDOUT_SPLIT for i in r.identities
        }
        assert not (trained & heldout)

    def test_ffpp_splits_into_500_pairs(self, records: list[VideoRecord]) -> None:
        """Verified on disk: FF++'s pairing graph is 500 components of size 2."""
        groups = {r.group for r in records if r.domain == "ffpp"}
        assert len(groups) == 500

    def test_training_balance_holds_after_splitting(
        self, records: list[VideoRecord]
    ) -> None:
        """Budget balance is designed on paper; this checks it survives the
        actual assignment, where whole groups move together."""
        train = [r for r in records if r.split == "train"]
        real = sum(r.frames for r in train if r.label == "real")
        fake = sum(r.frames for r in train if r.label == "fake")
        assert 0.85 <= fake / real <= 1.20, f"train is {fake / real:.2f}:1 fake:real"

    def test_every_training_domain_reaches_every_assigned_split(
        self, records: list[VideoRecord]
    ) -> None:
        for domain in ("ffpp", "dfd"):
            splits = {r.split for r in records if r.domain == domain}
            assert "train" in splits and "test" in splits

    def test_evaluation_sets_contain_both_classes(
        self, records: list[VideoRecord]
    ) -> None:
        """An evaluation slice with one class makes AUC undefined."""
        for split in ("val", "test", HELDOUT_SPLIT):
            labels = {r.label for r in records if r.split == split}
            assert labels == {"real", "fake"}, f"{split} has labels {labels}"

    def test_manifest_round_trips(
        self, records: list[VideoRecord], tmp_path: Path
    ) -> None:
        from falsora_ai.data.manifest import read_manifest, write_manifest

        path = write_manifest(records, tmp_path / "manifest.csv")
        loaded = read_manifest(path)
        assert sorted(loaded, key=lambda r: r.relpath) == sorted(
            records, key=lambda r: r.relpath
        )


class TestRecordIdentity:
    def test_video_id_is_stable_and_short(self) -> None:
        rec = make_record("a/b/c.mp4", ("ffpp:000",))
        assert rec.video_id == replace(rec, split="train").video_id
        assert len(rec.video_id) == 12

    def test_video_id_differs_by_path(self) -> None:
        a = make_record("a.mp4", ("ffpp:000",))
        b = make_record("b.mp4", ("ffpp:000",))
        assert a.video_id != b.video_id
