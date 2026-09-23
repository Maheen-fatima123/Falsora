"""Tests for Model Optimization (M7) — ONNX export, INT8 quantization,
latency benchmark.

Not testing that the exported/quantized model is *accurate* — that needs a
real trained M3 checkpoint and is exercised end to end in
``TestRealCheckpoint`` below (skipped when it's absent, e.g. CI). What unit
tests cover is the contract: export produces a valid, loadable ONNX graph;
quantization produces a valid, loadable INT8 graph (a direct regression test
for a real failure — see below); the fallback to untrained weights doesn't
crash; and the benchmark functions return sane, well-formed timing data.

Every model here is constructed with ``pretrained=False`` (no ImageNet
download) and no checkpoint override, same convention as
``test_engine_66.py``/``test_engine_67.py``.

Regression note: quantizing ``Conv`` nodes (onnxruntime's default dynamic-
quantization op set for CNNs) produces ``ConvInteger`` nodes that this
project's onnxruntime CPU build has no kernel for — the resulting model fails
to even load (``NOT_IMPLEMENTED`` at ``InferenceSession`` construction, not a
slow fallback). ``quantize.py`` restricts quantization to ``MatMul`` for this
reason; ``TestQuantize::test_quantized_model_is_loadable_and_runs`` exists so
that restriction can never silently regress.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("timm")
onnx = pytest.importorskip("onnx")
ort = pytest.importorskip("onnxruntime")

from falsora_ai.config import Config, ModelConfig, PathConfig  # noqa: E402
from falsora_ai.engine_66.deepfake.model import DeepfakeNet  # noqa: E402
from falsora_ai.engine_66.deepfake.train import load_checkpoint  # noqa: E402
from falsora_ai.optimization.benchmark import (  # noqa: E402
    LatencyResult,
    benchmark_onnx,
    benchmark_pytorch,
    benchmark_report,
    run_full_benchmark,
)
from falsora_ai.optimization.export_onnx import export_deepfake_to_onnx, onnx_path  # noqa: E402
from falsora_ai.optimization.quantize import int8_path, quantize_deepfake_onnx  # noqa: E402


def _tiny_cfg(tmp_path: Path) -> Config:
    """No pretrained download, everything routed to tmp_path so a test run
    never touches (or requires) the real project's checkpoints/ or models/."""
    return Config(
        paths=PathConfig(
            root=tmp_path,
            checkpoints=tmp_path / "checkpoints",
            models=tmp_path / "models",
        ),
        model=ModelConfig(architecture="efficientnet_b0", pretrained=False),
    )


class TestExport:
    def test_writes_a_valid_onnx_model(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        path = export_deepfake_to_onnx(cfg=cfg, device="cpu")

        assert path == onnx_path(cfg)
        assert path.exists()
        onnx.checker.check_model(onnx.load(str(path)))

    def test_falls_back_to_untrained_weights_without_a_checkpoint(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        assert not (cfg.paths.checkpoints / "efficientnet_b0_best.pt").exists()

        path = export_deepfake_to_onnx(cfg=cfg, device="cpu")

        assert path.exists()

    def test_exported_model_runs_and_matches_the_declared_io_names(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        path = export_deepfake_to_onnx(cfg=cfg, device="cpu")

        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        assert session.get_inputs()[0].name == "face_crop"
        assert session.get_outputs()[0].name == "logit"

        size = cfg.model.resolved_input_size()
        dummy = np.zeros((1, 3, size, size), dtype=np.float32)
        (logit,) = session.run(None, {"face_crop": dummy})
        assert logit.shape == (1, 1)


class TestQuantize:
    def test_raises_when_the_fp32_model_is_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.onnx"
        with pytest.raises(FileNotFoundError):
            quantize_deepfake_onnx(missing)

    def test_quantized_model_is_loadable_and_runs(self, tmp_path: Path) -> None:
        """Regression test for the ConvInteger NOT_IMPLEMENTED failure — see
        module docstring."""
        cfg = _tiny_cfg(tmp_path)
        fp32 = export_deepfake_to_onnx(cfg=cfg, device="cpu")

        path = quantize_deepfake_onnx(fp32)

        assert path == int8_path(fp32)
        assert path.exists()
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])  # must not raise
        size = cfg.model.resolved_input_size()
        dummy = np.zeros((1, 3, size, size), dtype=np.float32)
        (logit,) = session.run(None, {"face_crop": dummy})
        assert logit.shape == (1, 1)


class TestBenchmark:
    def test_benchmark_pytorch_returns_sane_timings(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        model = DeepfakeNet(cfg.model).eval()

        result = benchmark_pytorch(model, cfg.model.resolved_input_size(), n_runs=3, n_warmup=1)

        assert isinstance(result, LatencyResult)
        assert result.n_runs == 3
        assert result.min_ms <= result.median_ms <= result.max_ms
        assert result.mean_ms > 0.0

    def test_benchmark_onnx_returns_sane_timings(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        path = export_deepfake_to_onnx(cfg=cfg, device="cpu")

        result = benchmark_onnx(path, cfg.model.resolved_input_size(), n_runs=3, n_warmup=1)

        assert result.n_runs == 3
        assert result.mean_ms > 0.0

    def test_run_full_benchmark_covers_all_three_variants(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)

        results = run_full_benchmark(cfg=cfg, n_runs=3, n_warmup=1, device="cpu")

        assert set(results) == {"pytorch_fp32", "onnx_fp32", "onnx_int8"}
        report = benchmark_report(results)
        for label in results:
            assert label in report

    def test_report_flags_whether_the_live_path_meets_the_scope_claim(self, tmp_path: Path) -> None:
        cfg = _tiny_cfg(tmp_path)
        results = run_full_benchmark(cfg=cfg, n_runs=3, n_warmup=1, device="cpu")

        report = benchmark_report(results)

        assert "8-12 ms" in report


class TestRealCheckpoint:
    """End-to-end sanity check against the project's real, trained M3
    checkpoint — skipped when it isn't present (e.g. a fresh clone or CI)."""

    @pytest.fixture()
    def real_checkpoint(self) -> Path:
        cfg = Config()
        checkpoint = cfg.paths.checkpoints / f"{cfg.model.architecture}_best.pt"
        if not checkpoint.exists():
            pytest.skip("Real M3 checkpoint not present on this machine.")
        return checkpoint

    def test_onnx_output_matches_pytorch_for_the_same_weights(self, real_checkpoint: Path) -> None:
        """Both sides load the identical checkpoint, so this isolates export
        correctness from training — a graph bug (wrong op, wrong axis) would
        show up as a numeric mismatch even though both "worked" independently."""
        cfg = Config()
        model = DeepfakeNet(cfg.model)
        load_checkpoint(real_checkpoint, model, device="cpu")
        model.eval()

        path = export_deepfake_to_onnx(cfg=cfg, device="cpu")

        size = cfg.model.resolved_input_size()
        dummy = torch.zeros(1, 3, size, size)
        with torch.no_grad():
            expected = model(dummy).numpy()

        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        (actual,) = session.run(None, {"face_crop": dummy.numpy()})

        np.testing.assert_allclose(expected, actual, rtol=1e-4, atol=1e-5)
