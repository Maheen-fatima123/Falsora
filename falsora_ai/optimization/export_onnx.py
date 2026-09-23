"""
ONNX export — Model Optimization, live path (module 6.16 / scope 5.1).
==========================================================================

Scope section 5.1 commits to a **quantized EfficientNet-B0** for the live,
per-frame path — this is the only model this optimization module targets.
The static-path variants (B3/B4) exist to squeeze out accuracy on a single
uploaded image where a few hundred milliseconds is irrelevant; ONNX/INT8 only
matters where inference happens once per second, per open WebSocket
connection.

Exports the raw-logit graph, unchanged from :class:`DeepfakeNet.forward` —
the same convention ``engine_66/engine.py`` uses (model returns a logit,
sigmoid is applied once by the caller). Baking sigmoid into the ONNX graph
would silently double-apply it for any consumer that follows that same
convention.

Falls back to untrained weights (warns, does not raise) when no checkpoint is
on disk, matching ``ForgeryEngine``/``ExplanationEngine`` — this module must
also be exercisable, e.g. for the benchmark, on a fresh clone before M3 is
trained. A latency number from an untrained model is legitimate: architecture
and weight *values* do not change FLOPs or memory traffic, so measured
latency is identical either way.
"""

from __future__ import annotations

from pathlib import Path

import torch

from falsora_ai.common.logging import get_logger
from falsora_ai.config import Config
from falsora_ai.engine_66.deepfake.model import DeepfakeNet
from falsora_ai.engine_66.deepfake.train import load_checkpoint

__all__ = ["DEFAULT_OPSET", "onnx_path", "export_deepfake_to_onnx"]

logger = get_logger(__name__)

# onnxruntime>=1.17 (this project's floor, see pyproject.toml [optimize])
# fully supports opset 17; there is no reason to export at a lower one.
DEFAULT_OPSET = 17


def onnx_path(cfg: Config) -> Path:
    """Default fp32 ONNX export location for the configured architecture."""
    return cfg.paths.models / f"{cfg.model.architecture}.onnx"


def export_deepfake_to_onnx(
    cfg: Config | None = None,
    checkpoint: Path | None = None,
    output_path: Path | None = None,
    opset: int = DEFAULT_OPSET,
    device: str = "cpu",
) -> Path:
    """Export the trained deepfake model (fp32) to ONNX.

    Args:
        cfg: Resolves the backbone architecture, input resolution and
            checkpoint/output paths. Defaults to a fresh :class:`Config`.
        checkpoint: Override for the ``.pt`` checkpoint to load. Defaults to
            ``<architecture>_best.pt`` under ``cfg.paths.checkpoints``.
        output_path: Override for where the ``.onnx`` file is written.
            Defaults to :func:`onnx_path`.
        opset: ONNX opset version.
        device: Export always happens on CPU-shaped dummy input; ``device``
            only controls where the checkpoint is loaded/traced.

    Returns:
        The path the ONNX file was written to.
    """
    cfg = cfg or Config()
    model = DeepfakeNet(cfg.model)

    ckpt_path = checkpoint or cfg.paths.checkpoints / f"{cfg.model.architecture}_best.pt"
    if ckpt_path.exists():
        load_checkpoint(ckpt_path, model, device=device)
    else:
        logger.warning("No deepfake checkpoint at %s — exporting untrained weights.", ckpt_path)
    model.to(device).eval()

    size = cfg.model.resolved_input_size()
    dummy = torch.zeros(1, 3, size, size, device=device)

    out_path = output_path or onnx_path(cfg)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        dummy,
        str(out_path),
        input_names=["face_crop"],
        output_names=["logit"],
        # Batch dimension only — H/W are fixed by the resolved input size,
        # same as every other part of this pipeline (crop_face, transforms).
        dynamic_axes={"face_crop": {0: "batch"}, "logit": {0: "batch"}},
        opset_version=opset,
    )
    return out_path
