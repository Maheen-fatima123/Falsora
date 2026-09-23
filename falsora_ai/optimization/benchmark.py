"""
Latency benchmark — Model Optimization, live path.
=====================================================

Scope section 5.1 claims "~8-12 ms inference latency per frame on standard
CPU." ``ENGINEERING_PLAN.md`` section 6 records that number as currently
unverified — copied from literature, not measured on this project's own
hardware. This module produces the real number, for three variants of the
same model so the ONNX/INT8 work can be justified by an actual before/after
rather than assumed:

    1. PyTorch fp32  — what ``ForgeryEngine`` runs today
    2. ONNX fp32     — export overhead/benefit in isolation
    3. ONNX INT8     — the quantized live-path model scope 5.1 asks for
                       (only the head is actually quantized on this
                       platform — see ``quantize.py``'s module docstring)

Wall-clock, single-threaded-inference, CPU-only timing of a forward pass on a
single dummy input (matching the live path's one-frame-at-a-time call
pattern from module 6.16 — this is deliberately not a throughput/batch
benchmark). Warmup runs are discarded: the first few calls pay for lazy
kernel selection and allocator warm-up that a long-running live session never
repeats.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from falsora_ai.config import Config

__all__ = ["LatencyResult", "benchmark_pytorch", "benchmark_onnx", "run_full_benchmark", "benchmark_report"]

DEFAULT_WARMUP = 10
DEFAULT_RUNS = 100


@dataclass(frozen=True)
class LatencyResult:
    label: str
    n_runs: int
    mean_ms: float
    median_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float


def _stats(times_ms: list[float], label: str) -> LatencyResult:
    times_sorted = sorted(times_ms)
    p95_index = min(len(times_sorted) - 1, int(round(0.95 * (len(times_sorted) - 1))))
    return LatencyResult(
        label=label,
        n_runs=len(times_ms),
        mean_ms=statistics.mean(times_ms),
        median_ms=statistics.median(times_ms),
        p95_ms=times_sorted[p95_index],
        min_ms=min(times_ms),
        max_ms=max(times_ms),
    )


def benchmark_pytorch(
    model: torch.nn.Module,
    input_size: int,
    label: str = "pytorch_fp32",
    n_runs: int = DEFAULT_RUNS,
    n_warmup: int = DEFAULT_WARMUP,
    device: str = "cpu",
) -> LatencyResult:
    """Time ``n_runs`` forward passes of ``model`` on a single dummy input.

    ``model`` must already be in eval mode with the desired weights loaded —
    this function only times, it does not load checkpoints.
    """
    dummy = torch.zeros(1, 3, input_size, input_size, device=device)
    times_ms: list[float] = []
    with torch.no_grad():
        for _ in range(n_warmup):
            model(dummy)
        for _ in range(n_runs):
            t0 = time.perf_counter()
            model(dummy)
            times_ms.append((time.perf_counter() - t0) * 1000)
    return _stats(times_ms, label)


def benchmark_onnx(
    onnx_model_path: Path,
    input_size: int,
    label: str | None = None,
    n_runs: int = DEFAULT_RUNS,
    n_warmup: int = DEFAULT_WARMUP,
) -> LatencyResult:
    """Time ``n_runs`` ``InferenceSession.run`` calls against one dummy input.

    Local ``onnxruntime`` import: this function is only reachable from code
    that already intends to run ONNX inference, same rationale as torch
    imports elsewhere in ``engine_66``.
    """
    import onnxruntime as ort

    session = ort.InferenceSession(str(onnx_model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    dummy = np.zeros((1, 3, input_size, input_size), dtype=np.float32)

    times_ms: list[float] = []
    for _ in range(n_warmup):
        session.run(None, {input_name: dummy})
    for _ in range(n_runs):
        t0 = time.perf_counter()
        session.run(None, {input_name: dummy})
        times_ms.append((time.perf_counter() - t0) * 1000)

    return _stats(times_ms, label or onnx_model_path.name)


def run_full_benchmark(
    cfg: Config | None = None,
    n_runs: int = DEFAULT_RUNS,
    n_warmup: int = DEFAULT_WARMUP,
    device: str = "cpu",
) -> dict[str, LatencyResult]:
    """Export, quantize and benchmark all three variants in one call.

    Exercises the whole optimization pipeline end to end — the function the
    CLI's ``benchmark`` command and M7's own tests both call — rather than
    requiring export/quantize to have been run manually first.
    """
    from falsora_ai.engine_66.deepfake.model import DeepfakeNet
    from falsora_ai.engine_66.deepfake.train import load_checkpoint
    from falsora_ai.optimization.export_onnx import export_deepfake_to_onnx
    from falsora_ai.optimization.quantize import quantize_deepfake_onnx

    cfg = cfg or Config()
    size = cfg.model.resolved_input_size()

    model = DeepfakeNet(cfg.model)
    checkpoint = cfg.paths.checkpoints / f"{cfg.model.architecture}_best.pt"
    if checkpoint.exists():
        load_checkpoint(checkpoint, model, device=device)
    model.to(device).eval()

    fp32_path = export_deepfake_to_onnx(cfg=cfg, device=device)
    int8_path = quantize_deepfake_onnx(fp32_path)

    return {
        "pytorch_fp32": benchmark_pytorch(model, size, "pytorch_fp32", n_runs, n_warmup, device),
        "onnx_fp32": benchmark_onnx(fp32_path, size, "onnx_fp32", n_runs, n_warmup),
        "onnx_int8": benchmark_onnx(int8_path, size, "onnx_int8", n_runs, n_warmup),
    }


def benchmark_report(results: dict[str, LatencyResult]) -> str:
    """Human-readable table, and a flag against scope 5.1's 8-12 ms claim."""
    lines = ["Latency benchmark (CPU, single frame, ms)", "-" * 68]
    lines.append(f"{'variant':<16}{'mean':>8}{'median':>8}{'p95':>8}{'min':>8}{'max':>8}   n")
    for result in results.values():
        lines.append(
            f"{result.label:<16}{result.mean_ms:>8.2f}{result.median_ms:>8.2f}"
            f"{result.p95_ms:>8.2f}{result.min_ms:>8.2f}{result.max_ms:>8.2f}   {result.n_runs}"
        )

    live = results.get("onnx_int8")
    if live is not None:
        lines.append("")
        in_range = 8.0 <= live.mean_ms <= 12.0
        lines.append(
            f"Live-path (onnx_int8) mean: {live.mean_ms:.2f} ms — "
            + ("within" if in_range else "OUTSIDE")
            + " scope 5.1's claimed 8-12 ms; replace that figure with this measured one."
        )
    return "\n".join(lines)
