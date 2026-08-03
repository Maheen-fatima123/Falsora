"""Tests for frame sampling, crop geometry, and the resumable extraction ledger.

The crop geometry tests are the important ones. ``expand_box`` is called by the
offline extraction *and* by the live inference path, and a discrepancy between
them is invisible: no error, no warning, just a model performing worse than it
should for reasons that look like bad training. So the properties are pinned
here rather than left to inspection.

Torch is not required. The detector is stubbed, which is also the point of
having :class:`~falsora_ai.common.faces.FaceDetector` be a Protocol.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from falsora_ai.common.faces import Box, crop_face, expand_box
from falsora_ai.common.video import VideoReadError, sample_frame_indices
from falsora_ai.config import Config, FaceConfig
from falsora_ai.data.extract import (
    ExtractionResult,
    append_ledger,
    crop_dir_for,
    crop_name,
    extraction_report,
    load_ledger,
    write_crop_index,
)
from falsora_ai.data.manifest import VideoRecord


def record(**kw) -> VideoRecord:
    base = {
        "relpath": "FaceForensics++_C23/Deepfakes/000_003.mp4",
        "source": "FaceForensics++_C23/Deepfakes",
        "domain": "ffpp",
        "label": "fake",
        "role": "train_pool",
        "identities": ("ffpp:000", "ffpp:003"),
        "frames": 7,
        "group": "ffpp:000",
        "split": "train",
    }
    return VideoRecord(**{**base, **kw})


# --------------------------------------------------------------------------


class TestFrameSampling:
    def test_returns_the_requested_count(self) -> None:
        assert len(sample_frame_indices(500, 32)) == 32

    def test_indices_are_sorted_and_unique(self) -> None:
        idx = sample_frame_indices(500, 32)
        assert idx == sorted(set(idx))

    def test_indices_are_in_range(self) -> None:
        idx = sample_frame_indices(500, 32)
        assert idx[0] >= 0 and idx[-1] < 500

    def test_spans_the_whole_video(self) -> None:
        """The property that matters: sampling must not cluster at the start.

        Reading the first N frames of a talking-head clip yields N near-identical
        images, shrinking the effective dataset and overfitting one pose.
        """
        idx = sample_frame_indices(1000, 10)
        assert idx[0] < 100, "first sample is not near the start"
        assert idx[-1] > 900, "sampling never reaches the end of the video"

    def test_avoids_the_exact_endpoints(self) -> None:
        """Frame 0 is often a fade-in and the last frame a fade-out."""
        idx = sample_frame_indices(1000, 10)
        assert idx[0] != 0
        assert idx[-1] != 999

    def test_roughly_even_spacing(self) -> None:
        idx = sample_frame_indices(1000, 10)
        gaps = np.diff(idx)
        assert gaps.std() < 2.0, f"uneven spacing: {gaps}"

    def test_short_video_returns_every_frame_without_repeats(self) -> None:
        """Padding by repetition would put identical images in one batch."""
        assert sample_frame_indices(5, 32) == [0, 1, 2, 3, 4]

    def test_single_frame_video(self) -> None:
        assert sample_frame_indices(1, 8) == [0]

    def test_is_deterministic(self) -> None:
        assert sample_frame_indices(377, 13) == sample_frame_indices(377, 13)

    @pytest.mark.parametrize("total", [0, -1])
    def test_invalid_total_raises(self, total: int) -> None:
        with pytest.raises(VideoReadError):
            sample_frame_indices(total, 8)

    def test_invalid_wanted_raises(self) -> None:
        with pytest.raises(ValueError, match="wanted"):
            sample_frame_indices(100, 0)


class TestCropGeometry:
    """``expand_box`` is shared by training and inference. It must not drift."""

    def test_margin_expands_the_box(self) -> None:
        box = Box(100, 100, 200, 200)
        out = expand_box(box, 0.3, 1000, 1000)
        assert out.width == pytest.approx(130, abs=2)

    def test_zero_margin_keeps_the_size(self) -> None:
        out = expand_box(Box(100, 100, 200, 200), 0.0, 1000, 1000)
        assert out.width == pytest.approx(100, abs=1)

    def test_output_is_square(self) -> None:
        """Non-square crops get squashed by the model's resize, distorting
        facial proportions as a function of head pose — a shortcut feature."""
        out = expand_box(Box(100, 100, 200, 300), 0.3, 1000, 1000)
        assert abs(out.width - out.height) <= 1

    def test_centre_is_preserved(self) -> None:
        box = Box(100, 100, 200, 200)
        out = expand_box(box, 0.3, 1000, 1000)
        assert (out.x1 + out.x2) / 2 == pytest.approx(150, abs=2)
        assert (out.y1 + out.y2) / 2 == pytest.approx(150, abs=2)

    def test_stays_inside_the_frame(self) -> None:
        out = expand_box(Box(0, 0, 100, 100), 0.5, 640, 480)
        assert out.x1 >= 0 and out.y1 >= 0
        assert out.x2 <= 640 and out.y2 <= 480

    def test_edge_face_keeps_its_scale(self) -> None:
        """The subtle one. Naive clipping shrinks crops near the frame border,
        so edge-of-frame and profile faces — the hard cases — silently arrive at
        a different scale from centred ones."""
        centred = expand_box(Box(300, 200, 400, 300), 0.3, 640, 480)
        cornered = expand_box(Box(0, 0, 100, 100), 0.3, 640, 480)
        assert cornered.width == pytest.approx(centred.width, abs=2)

    def test_box_larger_than_frame_is_clamped(self) -> None:
        out = expand_box(Box(0, 0, 640, 480), 0.5, 640, 480)
        assert out.width <= 640 and out.height <= 480

    def test_negative_margin_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="margin"):
            expand_box(Box(0, 0, 10, 10), -0.1, 100, 100)

    def test_geometry_matches_configured_margin(self) -> None:
        """Pins the training/inference contract to the config value itself, so
        changing FaceConfig.margin cannot silently desynchronise the paths."""
        face = FaceConfig()
        out = expand_box(Box(100, 100, 200, 200), face.margin, 1000, 1000)
        assert out.width == pytest.approx(100 * (1 + face.margin), abs=2)


class TestCropRendering:
    def test_output_shape_and_dtype(self) -> None:
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        face = FaceConfig(crop_size=300)
        crop = crop_face(frame, Box(100, 100, 250, 250), face)
        assert crop.shape == (300, 300, 3)
        assert crop.dtype == np.uint8

    def test_small_face_is_upscaled_not_padded(self) -> None:
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        crop = crop_face(frame, Box(10, 10, 50, 50), FaceConfig(crop_size=300))
        assert crop.shape == (300, 300, 3)

    def test_edge_face_produces_a_full_crop(self) -> None:
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        crop = crop_face(frame, Box(0, 0, 80, 80), FaceConfig(crop_size=300))
        assert crop.shape == (300, 300, 3)


class TestBox:
    def test_size_is_the_shorter_side(self) -> None:
        assert Box(0, 0, 100, 60).size == 60

    def test_dimensions(self) -> None:
        box = Box(10, 20, 110, 140)
        assert (box.width, box.height) == (100, 120)


class TestCropPaths:
    def test_directory_separates_split_and_label(self) -> None:
        """A training run reading the wrong path must find an empty directory
        rather than contaminated data."""
        path = crop_dir_for(Path("/crops"), record(split="test", label="real"))
        assert path == Path("/crops/test/real")

    def test_name_embeds_the_frame_index(self) -> None:
        """Every crop must be traceable to a timestamp for the 6.7 evidence trail."""
        assert crop_name(record(), 42).endswith("_f00042.jpg")

    def test_names_are_unique_across_videos(self) -> None:
        a = crop_name(record(relpath="a/b.mp4"), 10)
        b = crop_name(record(relpath="a/c.mp4"), 10)
        assert a != b

    def test_name_is_filesystem_safe(self) -> None:
        """Source paths contain spaces and ``++``; crop names must not."""
        name = crop_name(record(relpath="Celeb DF/Celeb-real/id0_0000.mp4"), 1)
        assert " " not in name and "+" not in name


class TestLedger:
    def test_missing_ledger_is_empty_not_an_error(self, tmp_path: Path) -> None:
        assert load_ledger(tmp_path / "nope.jsonl") == {}

    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        result = ExtractionResult("a/b.mp4", "ok", crops=("x.jpg", "y.jpg"), frames_requested=7)
        append_ledger(path, result)
        assert load_ledger(path)["a/b.mp4"] == result

    def test_appends_rather_than_overwrites(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        append_ledger(path, ExtractionResult("a.mp4", "ok"))
        append_ledger(path, ExtractionResult("b.mp4", "no_face"))
        assert set(load_ledger(path)) == {"a.mp4", "b.mp4"}

    def test_truncated_final_line_is_survivable(self, tmp_path: Path) -> None:
        """A hard kill mid-write must not make the whole run unresumable."""
        path = tmp_path / "ledger.jsonl"
        append_ledger(path, ExtractionResult("a.mp4", "ok"))
        with path.open("a") as fh:
            fh.write('{"relpath": "b.mp4", "stat')  # cut off

        loaded = load_ledger(path)
        assert set(loaded) == {"a.mp4"}  # good line kept, partial line dropped

    def test_statuses_survive_the_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        for status in ("ok", "no_face", "unreadable"):
            append_ledger(path, ExtractionResult(f"{status}.mp4", status, detail="why"))
        loaded = load_ledger(path)
        assert {r.status for r in loaded.values()} == {"ok", "no_face", "unreadable"}
        assert all(r.detail == "why" for r in loaded.values())

    def test_written_lines_are_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.jsonl"
        append_ledger(path, ExtractionResult("Celeb DF/x.mp4", "ok", crops=("a b.jpg",)))
        for line in path.read_text().splitlines():
            json.loads(line)


class TestExtractionReport:
    def test_counts_are_reported_per_split(self) -> None:
        records = [record(relpath="a.mp4", split="train"), record(relpath="b.mp4", split="val")]
        results = {
            "a.mp4": ExtractionResult("a.mp4", "ok", crops=("1.jpg", "2.jpg")),
            "b.mp4": ExtractionResult("b.mp4", "ok", crops=("3.jpg",)),
        }
        text = extraction_report(records, results)
        assert "train" in text and "val" in text

    def test_high_loss_produces_a_warning(self) -> None:
        """Silent detection loss shifts the class balance the budget was tuned
        for; it has to be visible."""
        records = [record(relpath=f"{i}.mp4") for i in range(10)]
        results = {
            f"{i}.mp4": ExtractionResult(f"{i}.mp4", "no_face" if i < 3 else "ok", crops=("c.jpg",))
            for i in range(10)
        }
        assert "WARNING" in extraction_report(records, results)

    def test_clean_run_produces_no_warning(self) -> None:
        records = [record(relpath=f"{i}.mp4") for i in range(10)]
        results = {
            f"{i}.mp4": ExtractionResult(f"{i}.mp4", "ok", crops=("c.jpg",))
            for i in range(10)
        }
        assert "WARNING" not in extraction_report(records, results)

    def test_pending_videos_do_not_crash_the_report(self) -> None:
        extraction_report([record(relpath="a.mp4")], {})


class TestCropIndex:
    def test_only_successful_videos_are_indexed(self, tmp_path: Path) -> None:
        records = [record(relpath="a.mp4"), record(relpath="b.mp4")]
        results = {
            "a.mp4": ExtractionResult("a.mp4", "ok", crops=("1.jpg", "2.jpg")),
            "b.mp4": ExtractionResult("b.mp4", "no_face"),
        }
        path = write_crop_index(records, results, tmp_path / "crops.csv")
        rows = path.read_text().splitlines()
        assert len(rows) == 3  # header + 2 crops

    def test_row_carries_split_and_label(self, tmp_path: Path) -> None:
        """The M2 Dataset reads this file with no joins and no knowledge of the
        directory layout."""
        records = [record(relpath="a.mp4", split="val", label="real")]
        results = {"a.mp4": ExtractionResult("a.mp4", "ok", crops=("1.jpg",))}
        path = write_crop_index(records, results, tmp_path / "crops.csv")
        header, row = path.read_text().splitlines()
        fields = dict(zip(header.split(","), row.split(","), strict=True))
        assert fields["split"] == "val"
        assert fields["label"] == "real"
        assert fields["video_relpath"] == "a.mp4"

    def test_ledger_entry_for_a_dropped_video_is_ignored(self, tmp_path: Path) -> None:
        """The ledger outlives manifest edits; a stale entry must not crash."""
        results = {"gone.mp4": ExtractionResult("gone.mp4", "ok", crops=("1.jpg",))}
        path = write_crop_index([], results, tmp_path / "crops.csv")
        assert len(path.read_text().splitlines()) == 1  # header only


class TestConfigWiring:
    def test_crop_size_covers_the_planned_architectures(self) -> None:
        """Crops are stored larger than the model input so that changing
        backbone does not force a six-hour re-extraction.

        300 px covers EfficientNet-B0 (224), B3 (300) and Xception (299).
        It does **not** cover B4 (320): moving to B4 means either re-extracting
        or upscaling crops, and upscaling destroys exactly the high-frequency
        detail the model reads. That trade-off should be a deliberate decision,
        so this test states the limit rather than hiding it.
        """
        from falsora_ai.config import ModelConfig

        cfg = Config()
        covered = {"efficientnet_b0", "efficientnet_b3", "xception"}
        for arch in covered:
            assert cfg.face.crop_size >= ModelConfig(architecture=arch).resolved_input_size()
        assert cfg.model.architecture in covered, (
            f"{cfg.model.architecture} needs an input larger than the "
            f"{cfg.face.crop_size}px stored crops; re-extract before using it."
        )
