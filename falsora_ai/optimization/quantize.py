"""
INT8 dynamic quantization — Model Optimization, live path.
==============================================================

Dynamic (not static/QAT) quantization: weights are quantized once, ahead of
time, activations are quantized on the fly per inference call. No calibration
dataset is required, which matters here because M3's face-crop dataset is
several GB and this step should be runnable from just a checkpoint. The
tradeoff — static quantization typically yields a faster INT8 model — is
exactly what ``benchmark.py`` exists to quantify for this project's actual
hardware rather than assume from literature.

**``Conv`` is deliberately excluded** (``op_types_to_quantize=["MatMul"]``
below), even though it dominates EfficientNet's FLOPs and is one of
onnxruntime's documented dynamic-quantization op types. Quantizing it here
produces ``ConvInteger`` nodes that this project's onnxruntime CPU build does
not implement a kernel for (``NOT_IMPLEMENTED`` at session creation, not a
slow fallback — the exported model would not load at all). This is a known,
platform-dependent gap in ONNX Runtime's dynamic-quantization support for
CNNs, not specific to this model. The practical consequence: only the tiny
``nn.Linear`` head gets quantized, so most of the INT8 speedup a CNN could
theoretically get is not realised by *dynamic* quantization here — static
(calibration-based) quantization would be needed for that, and is out of
scope for this pass. ``benchmark.py`` measures and reports the real number
this actually produces rather than the number a fully-quantized backbone
would.
"""

from __future__ import annotations

from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic

__all__ = ["int8_path", "quantize_deepfake_onnx"]

# See the module docstring: Conv is excluded because ConvInteger has no
# kernel in this project's onnxruntime CPU build.
_QUANTIZABLE_OPS = ["MatMul"]


def int8_path(fp32_path: Path) -> Path:
    """Default INT8 output location, derived from the fp32 ONNX path."""
    return fp32_path.with_name(f"{fp32_path.stem}_int8.onnx")


def quantize_deepfake_onnx(fp32_path: Path, output_path: Path | None = None) -> Path:
    """Dynamically INT8-quantize an exported fp32 ONNX model.

    Args:
        fp32_path: Output of :func:`falsora_ai.optimization.export_onnx.export_deepfake_to_onnx`.
        output_path: Defaults to :func:`int8_path`.

    Returns:
        The path the quantized model was written to.

    Raises:
        FileNotFoundError: ``fp32_path`` does not exist — quantization has
            nothing to read, and a silent no-op here would make ``benchmark``
            report timings for whatever INT8 file happened to already be on
            disk instead of the one just requested.
    """
    if not fp32_path.exists():
        raise FileNotFoundError(
            f"No fp32 ONNX model at {fp32_path} — run export_deepfake_to_onnx() first."
        )

    out_path = output_path or int8_path(fp32_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    quantize_dynamic(
        str(fp32_path),
        str(out_path),
        weight_type=QuantType.QInt8,
        op_types_to_quantize=_QUANTIZABLE_OPS,
    )
    return out_path
