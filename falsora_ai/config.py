"""
Falsora AI Engine — Configuration
=================================

Replaces the original ``utils/config.py``, which had two problems: it executed
side effects at import time (created directories, printed the device), and it
exposed mutable module-level globals that any module could silently depend on.

Here configuration is an immutable dataclass that is *constructed* and *passed*.
Importing this module does nothing observable.

Usage
-----
    from falsora_ai.config import Config, DataConfig

    cfg = Config()                              # defaults
    cfg = Config(train=TrainConfig(epochs=30))  # override
    cfg = Config.from_yaml("configs/b4.yaml")   # from file
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "PROJECT_ROOT",
    "PathConfig",
    "DataConfig",
    "FaceConfig",
    "ModelConfig",
    "TrainConfig",
    "LiveConfig",
    "Config",
]

# Repository root: falsora_ai/config.py -> falsora_ai/ -> <root>
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PathConfig:
    """Filesystem layout. Nothing is created at construction time.

    Call :meth:`ensure` explicitly when a script actually intends to write.
    """

    root: Path = PROJECT_ROOT

    raw_datasets: Path = PROJECT_ROOT / "raw_datasets"
    face_crops: Path = PROJECT_ROOT / "face_crops"
    manifests: Path = PROJECT_ROOT / "manifests"

    models: Path = PROJECT_ROOT / "models"
    checkpoints: Path = PROJECT_ROOT / "checkpoints"
    outputs: Path = PROJECT_ROOT / "outputs"
    gradcam: Path = PROJECT_ROOT / "gradcam"
    logs: Path = PROJECT_ROOT / "logs"

    @property
    def video_manifest(self) -> Path:
        """Video-level manifest: one row per source video, with split assignment."""
        return self.manifests / "videos.csv"

    @property
    def crop_manifest(self) -> Path:
        """Crop-level manifest: one row per extracted face crop."""
        return self.manifests / "crops.csv"

    @property
    def splits_file(self) -> Path:
        """Frozen identity-disjoint split assignment. Written once, never edited."""
        return self.manifests / "splits.json"

    def ensure(self) -> None:
        """Create writable output directories. Never touches input directories."""
        for p in (
            self.face_crops,
            self.manifests,
            self.models,
            self.checkpoints,
            self.outputs,
            self.gradcam,
            self.logs,
        ):
            p.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DataConfig:
    """Dataset composition and the frame budget.

    ``frames_per_video`` is deliberately per-source rather than global. It is
    tuned so real and fake are balanced *within every domain*, which removes the
    need for class re-weighting later. See ENGINEERING_PLAN.md section 3.5.

    ``EXCLUDED_SOURCES`` documents a verified finding: every file in
    ``raw_datasets/FF++/fake`` is also in
    ``raw_datasets/FaceForensics++_C23/DeepFakeDetection``. Including both would
    double-count those videos and risk placing one video in two splits.
    """

    # source directory (relative to raw_datasets) -> label
    SOURCE_LABELS: dict[str, str] = field(
        default_factory=lambda: {
            "FaceForensics++_C23/original": "real",
            "FaceForensics++_C23/Deepfakes": "fake",
            "FaceForensics++_C23/Face2Face": "fake",
            "FaceForensics++_C23/FaceSwap": "fake",
            "FaceForensics++_C23/FaceShifter": "fake",
            "FaceForensics++_C23/NeuralTextures": "fake",
            "FaceForensics++_C23/DeepFakeDetection": "fake",
            "FF++/real": "real",  # DFD actor originals — the ONLY real counterpart to DFD
            "Celeb DF/Celeb-real": "real",
            "Celeb DF/YouTube-real": "real",
            "Celeb DF/Celeb-synthesis": "fake",
        }
    )

    # Verified duplicate — see ENGINEERING_PLAN.md section 1.3.
    EXCLUDED_SOURCES: tuple[str, ...] = ("FF++/fake",)

    frames_per_video: dict[str, int] = field(
        default_factory=lambda: {
            "FaceForensics++_C23/original": 32,
            "FaceForensics++_C23/Deepfakes": 7,
            "FaceForensics++_C23/Face2Face": 7,
            "FaceForensics++_C23/FaceSwap": 7,
            "FaceForensics++_C23/FaceShifter": 7,
            "FaceForensics++_C23/NeuralTextures": 7,
            "FaceForensics++_C23/DeepFakeDetection": 7,
            "FF++/real": 32,
            "Celeb DF/Celeb-real": 32,
            "Celeb DF/YouTube-real": 32,
            "Celeb DF/Celeb-synthesis": 5,
        }
    )

    # Domain grouping, used for split logic and cross-dataset evaluation.
    domain_of: dict[str, str] = field(
        default_factory=lambda: {
            "FaceForensics++_C23/original": "ffpp",
            "FaceForensics++_C23/Deepfakes": "ffpp",
            "FaceForensics++_C23/Face2Face": "ffpp",
            "FaceForensics++_C23/FaceSwap": "ffpp",
            "FaceForensics++_C23/FaceShifter": "ffpp",
            "FaceForensics++_C23/NeuralTextures": "ffpp",
            "FaceForensics++_C23/DeepFakeDetection": "dfd",
            "FF++/real": "dfd",
            "Celeb DF/Celeb-real": "celebdf",
            "Celeb DF/YouTube-real": "celebdf",
            "Celeb DF/Celeb-synthesis": "celebdf",
        }
    )

    video_extensions: tuple[str, ...] = (".mp4", ".avi", ".mov", ".mkv")

    # Split ratios. Celeb-DF ignores these in favour of its official
    # List_of_testing_videos.txt, which is present on disk.
    train_ratio: float = 0.72
    val_ratio: float = 0.14
    test_ratio: float = 0.14
    split_seed: int = 231659  # Maheen's registration number — memorable and fixed

    def frames_for(self, source: str) -> int:
        return self.frames_per_video.get(source, 8)


# --------------------------------------------------------------------------
# Face detection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceConfig:
    """Face detection and cropping.

    ``margin`` is the fraction of context added around the detector box. It MUST
    be identical at training and inference time; a model trained on tight crops
    and served loose crops loses a large amount of accuracy for no obvious
    reason. 0.3 follows the FaceForensics++ reference implementation.
    """

    detector: Literal["mtcnn", "haar"] = "mtcnn"
    crop_size: int = 300  # stored on disk; models downscale from here
    margin: float = 0.3
    min_face_size: int = 60  # pixels; smaller detections are discarded
    min_confidence: float = 0.90
    largest_face_only: bool = True  # these datasets are single-subject
    jpeg_quality: int = 95


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelConfig:
    """Backbone selection.

    ``efficientnet_b0`` at 224 is the live path mandated by scope section 5.1.
    ``efficientnet_b3``/``b4`` are the static path. Train B0 first: it proves the
    whole pipeline in under two GPU-hours.
    """

    architecture: str = "efficientnet_b0"
    input_size: int = 224
    pretrained: bool = True
    num_classes: int = 1  # single logit + BCEWithLogits
    dropout: float = 0.3

    INPUT_SIZES: dict[str, int] = field(
        default_factory=lambda: {
            "efficientnet_b0": 224,
            "efficientnet_b1": 240,
            "efficientnet_b2": 260,
            "efficientnet_b3": 300,
            "efficientnet_b4": 320,
            "xception": 299,
        }
    )

    def resolved_input_size(self) -> int:
        return self.INPUT_SIZES.get(self.architecture, self.input_size)


# --------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TrainConfig:
    batch_size: int = 32
    epochs: int = 12
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    warmup_epochs: int = 1
    label_smoothing: float = 0.05
    num_workers: int = 4
    mixed_precision: bool = True
    grad_clip: float = 1.0

    early_stopping_patience: int = 4
    monitor_metric: str = "val_auc"

    # Checkpoint every epoch. Colab sessions die; resuming must always work.
    checkpoint_every_epoch: bool = True
    seed: int = 231659


# --------------------------------------------------------------------------
# Live stream (modules 6.16 + optimization)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveConfig:
    """Live-stream parameters, taken directly from the scope document.

    Thresholds are expressed as **authenticity** (higher = more genuine) to
    match scope section 5.1 Stage 4: "If the rolling score drops below the
    HIGH-RISK threshold (< 0.35 authenticity)".
    """

    buffer_size: int = 5  # scope 6.16: "last 5 frames"
    capture_fps: float = 1.0  # scope 5.1 Stage 1

    high_risk_threshold: float = 0.35  # scope 5.1 Stage 4
    watch_threshold: float = 0.55  # intermediate caution band

    # Hysteresis: once HIGH_RISK, authenticity must recover above
    # high_risk_threshold + hysteresis to clear. Prevents alert flapping when
    # the score oscillates around the threshold.
    hysteresis: float = 0.05

    min_frames_for_verdict: int = 3  # below this, report INSUFFICIENT_DATA
    downweight_low_quality: float = 0.5  # weight for frames flagged by 6.15
    save_evidence_on_alert: bool = True

    def __post_init__(self) -> None:
        if not 0.0 < self.high_risk_threshold < self.watch_threshold < 1.0:
            raise ValueError(
                "Require 0 < high_risk_threshold < watch_threshold < 1; got "
                f"{self.high_risk_threshold} and {self.watch_threshold}."
            )
        if self.min_frames_for_verdict > self.buffer_size:
            raise ValueError(
                f"min_frames_for_verdict ({self.min_frames_for_verdict}) exceeds "
                f"buffer_size ({self.buffer_size}); a verdict could never be reached."
            )


# --------------------------------------------------------------------------
# Root
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    paths: PathConfig = field(default_factory=PathConfig)
    data: DataConfig = field(default_factory=DataConfig)
    face: FaceConfig = field(default_factory=FaceConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    live: LiveConfig = field(default_factory=LiveConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def replace(self, **changes: Any) -> Config:
        """Return a modified copy. The original is never mutated."""
        return replace(self, **changes)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        """Load overrides from YAML. Only top-level sections may be overridden."""
        import yaml  # local import: YAML is not needed for the common path

        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}

        section_types = {
            "paths": PathConfig,
            "data": DataConfig,
            "face": FaceConfig,
            "model": ModelConfig,
            "train": TrainConfig,
            "live": LiveConfig,
        }
        unknown = set(raw) - set(section_types)
        if unknown:
            raise ValueError(
                f"Unknown config section(s): {sorted(unknown)}. "
                f"Valid sections: {sorted(section_types)}"
            )
        kwargs = {name: section_types[name](**raw[name]) for name in raw}
        return cls(**kwargs)


def resolve_device(prefer: str | None = None) -> str:
    """Return the best available torch device as a string.

    Kept as a *function* rather than a module constant so that importing
    ``config`` never imports torch. The original ``utils/config.py`` imported
    torch and printed the device at import time, which made every module that
    touched configuration pay for a CUDA initialisation.
    """
    if prefer:
        return prefer
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
