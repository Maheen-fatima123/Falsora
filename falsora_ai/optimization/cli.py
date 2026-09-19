"""
Command line for Model Optimization (module M7).
====================================================

    python -m falsora_ai.optimization export      # fp32 ONNX export
    python -m falsora_ai.optimization quantize     # INT8 dynamic quantization
    python -m falsora_ai.optimization benchmark    # export + quantize + latency, all three variants

``benchmark`` runs ``export`` and ``quantize`` itself if their outputs are
missing, so it is the one command actually needed to reproduce M7's headline
number end to end.
"""

from __future__ import annotations

import argparse

from falsora_ai.config import Config
from falsora_ai.optimization.benchmark import benchmark_report, run_full_benchmark
from falsora_ai.optimization.export_onnx import export_deepfake_to_onnx
from falsora_ai.optimization.quantize import int8_path, quantize_deepfake_onnx


def cmd_export(cfg: Config, args: argparse.Namespace) -> int:
    path = export_deepfake_to_onnx(cfg=cfg, device=args.device)
    print(f"Exported fp32 ONNX model to {path}")
    return 0


def cmd_quantize(cfg: Config, args: argparse.Namespace) -> int:
    from falsora_ai.optimization.export_onnx import onnx_path

    fp32 = onnx_path(cfg)
    if not fp32.exists():
        print(f"No fp32 ONNX model at {fp32}. Run `export` first.")
        return 1

    path = quantize_deepfake_onnx(fp32, int8_path(fp32))
    print(f"Quantized INT8 model written to {path}")
    return 0


def cmd_benchmark(cfg: Config, args: argparse.Namespace) -> int:
    results = run_full_benchmark(cfg=cfg, n_runs=args.runs, n_warmup=args.warmup, device=args.device)
    print(benchmark_report(results))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m falsora_ai.optimization",
        description="Falsora AI engine — ONNX export, INT8 quantization, latency benchmark (module M7).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="export the trained deepfake model to fp32 ONNX")
    export.add_argument("--device", default="cpu")

    sub.add_parser("quantize", help="INT8-quantize the exported fp32 ONNX model")

    benchmark = sub.add_parser("benchmark", help="measure CPU latency: pytorch fp32, onnx fp32, onnx int8")
    benchmark.add_argument("--runs", type=int, default=100)
    benchmark.add_argument("--warmup", type=int, default=10)
    benchmark.add_argument("--device", default="cpu")

    args = parser.parse_args(argv)
    cfg = Config()

    handlers = {
        "export": cmd_export,
        "quantize": cmd_quantize,
        "benchmark": cmd_benchmark,
    }
    return handlers[args.command](cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
