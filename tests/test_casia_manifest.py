"""Tests for the CASIA v2.0 manifest builder.

Synthetic tests build a miniature CASIA-shaped directory tree under
``tmp_path`` so the suite never depends on the 1.2 GB real download. The real
download is exercised separately in :class:`TestAgainstRealDataset`, which
skips cleanly when it is absent (mirrors ``tests/test_splits.py``'s
``needs_datasets`` pattern).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from falsora_ai.config import Config, TamperingConfig
from falsora_ai.data.casia_manifest import (
    CASIA_MANIFEST_VERSION,
    ImageRecord,
    build_casia_manifest,
    read_casia_manifest,
    summarise_casia,
    write_casia_manifest,
)
from falsora_ai.data.identity import IdentityParseError

CASIA_ROOT = Config().paths.casia_root
needs_casia = pytest.mark.skipif(
    not CASIA_ROOT.is_dir(), reason="raw_datasets/CASIA2 not present (1.2 GB, gitignored)"
)


def _write_jpeg(path: Path) -> None:
    """A 4x4 real JPEG — enough for PIL/cv2 to decode later if a test needs to."""
    import numpy as np

    cv2 = pytest.importorskip("cv2")
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.zeros((4, 4, 3), dtype=np.uint8))


def _make_casia_tree(root: Path) -> None:
    (root / "Au").mkdir(parents=True)
    (root / "Tp").mkdir(parents=True)
    (root / "CASIA 2 Groundtruth").mkdir(parents=True)

    _write_jpeg(root / "Au" / "Au_ani_00018.jpg")
    _write_jpeg(root / "Au" / "Au_sec_00096.jpg")
    (root / "Au" / "Thumbs.db").write_bytes(b"")  # must be skipped, not parsed

    _write_jpeg(root / "Tp" / "Tp_D_CND_M_N_ani00018_sec00096_00138.tif")
    (root / "CASIA 2 Groundtruth" / "Tp_D_CND_M_N_ani00018_sec00096_00138_gt.png").write_bytes(
        b""
    )


class TestBuildManifest:
    def test_scans_authentic_and_tampered_images(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        records = build_casia_manifest(tmp_path)
        assert {r.label for r in records} == {"authentic", "tampered"}
        assert len(records) == 3  # 2 Au + 1 Tp

    def test_thumbs_db_is_skipped(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        records = build_casia_manifest(tmp_path)
        assert all("Thumbs.db" not in r.relpath for r in records)

    def test_tampered_image_carries_both_sources(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        records = build_casia_manifest(tmp_path)
        tp = next(r for r in records if r.label == "tampered")
        assert tp.sources == ("casia:ani18", "casia:sec96")

    def test_tampered_image_has_a_mask(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        records = build_casia_manifest(tmp_path)
        tp = next(r for r in records if r.label == "tampered")
        assert tp.mask_relpath.endswith("_gt.png")

    def test_authentic_image_has_no_mask(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        records = build_casia_manifest(tmp_path)
        au = [r for r in records if r.label == "authentic"]
        assert all(r.mask_relpath == "" for r in au)

    def test_missing_root_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_casia_manifest(tmp_path / "does_not_exist")

    def test_missing_mask_raises(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        (tmp_path / "CASIA 2 Groundtruth" / "Tp_D_CND_M_N_ani00018_sec00096_00138_gt.png").unlink()
        with pytest.raises(FileNotFoundError, match="ground-truth mask"):
            build_casia_manifest(tmp_path)

    def test_mask_with_mistyped_source_id_is_found_by_sequence_number(
        self, tmp_path: Path
    ) -> None:
        """CASIA v2.0 ships 142 masks whose name disagrees with their Tp
        image on the source id or splice flag, e.g. a real mask named
        ``..._arc00086_xxx00000_00306_gt.png`` for
        ``Tp_..._arc00086_arc00086_00306.tif``. The trailing sequence number
        (``00306``) still matches, so the manifest must still resolve it
        rather than treating the dataset's own typo as a corrupt download."""
        _make_casia_tree(tmp_path)
        gt_dir = tmp_path / "CASIA 2 Groundtruth"
        (gt_dir / "Tp_D_CND_M_N_ani00018_sec00096_00138_gt.png").rename(
            gt_dir / "Tp_D_CND_M_N_ani00018_xxx00000_00138_gt.png"
        )
        records = build_casia_manifest(tmp_path)
        tp = next(r for r in records if r.label == "tampered")
        assert tp.mask_relpath.endswith("Tp_D_CND_M_N_ani00018_xxx00000_00138_gt.png")

    def test_malformed_filename_raises(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        _write_jpeg(tmp_path / "Au" / "not_a_valid_name.jpg")
        with pytest.raises(IdentityParseError):
            build_casia_manifest(tmp_path)

    def test_empty_dataset_raises(self, tmp_path: Path) -> None:
        (tmp_path / "Au").mkdir(parents=True)
        (tmp_path / "Tp").mkdir(parents=True)
        (tmp_path / "CASIA 2 Groundtruth").mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="No CASIA images found"):
            build_casia_manifest(tmp_path)


class TestRoundTrip:
    def test_manifest_round_trips(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        records = build_casia_manifest(tmp_path)
        path = write_casia_manifest(records, tmp_path / "casia.csv")
        loaded = read_casia_manifest(path)
        assert sorted(loaded, key=lambda r: r.relpath) == sorted(records, key=lambda r: r.relpath)

    def test_rejects_wrong_version_banner(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.csv"
        path.write_text("# not a falsora casia manifest\n")
        with pytest.raises(ValueError, match="not a falsora CASIA manifest"):
            read_casia_manifest(path)

    def test_rejects_incompatible_major_version(self, tmp_path: Path) -> None:
        path = tmp_path / "casia.csv"
        path.write_text(f"# falsora casia manifest v{int(CASIA_MANIFEST_VERSION[0]) + 1}.0.0\n")
        with pytest.raises(ValueError, match="this code writes"):
            read_casia_manifest(path)


class TestSummarise:
    def test_reports_totals_by_label(self, tmp_path: Path) -> None:
        _make_casia_tree(tmp_path)
        records = build_casia_manifest(tmp_path)
        out = summarise_casia(records)
        assert "authentic" in out and "tampered" in out
        assert "3" in out  # total


class TestRecordIdentity:
    def test_image_id_is_stable_and_short(self) -> None:
        rec = ImageRecord(relpath="Au/Au_ani_00018.jpg", label="authentic", sources=("casia:ani18",))
        assert len(rec.image_id) == 12
        assert rec.image_id == ImageRecord(
            relpath="Au/Au_ani_00018.jpg", label="authentic", sources=("casia:ani18",), split="train"
        ).image_id

    def test_image_id_differs_by_path(self) -> None:
        a = ImageRecord(relpath="Au/a.jpg", label="authentic", sources=("casia:a1",))
        b = ImageRecord(relpath="Au/b.jpg", label="authentic", sources=("casia:a1",))
        assert a.image_id != b.image_id


@needs_casia
class TestAgainstRealDataset:
    """The properties that matter, checked on the actual 12,614 files.

    Skipped in CI, run locally before any tampering-branch training job.
    """

    @pytest.fixture(scope="class")
    def records(self) -> list[ImageRecord]:
        return build_casia_manifest(CASIA_ROOT, TamperingConfig())

    def test_matches_the_scope_document_counts(self, records: list[ImageRecord]) -> None:
        authentic = [r for r in records if r.label == "authentic"]
        tampered = [r for r in records if r.label == "tampered"]
        assert len(authentic) == 7491
        assert len(tampered) == 5123

    def test_every_tampered_image_resolves_to_an_existing_source(
        self, records: list[ImageRecord]
    ) -> None:
        au_sources = {r.sources[0] for r in records if r.label == "authentic"}
        tampered = [r for r in records if r.label == "tampered"]
        missing = [r.relpath for r in tampered if not all(s in au_sources for s in r.sources)]
        assert not missing, f"Tp images with a source id absent from Au: {missing[:5]}"
