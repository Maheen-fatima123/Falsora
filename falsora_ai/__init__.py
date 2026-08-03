"""
Falsora AI & Forensic Engine
============================

Modules 6.6, 6.7, 6.16 and Model Optimization of the Falsora system.
Owner: Maheen Fatima (231659).

Importing this package is cheap: it pulls in the integration contracts and
configuration only. Torch, OpenCV and model weights are loaded lazily by the
submodule that needs them, so Ujala's API layer and Mehreen's decision engine
can ``from falsora_ai.contracts import ForgeryResult`` without installing CUDA.
"""

from falsora_ai.config import Config
from falsora_ai.contracts import (
    SCHEMA_VERSION,
    AnalysisMode,
    Explanation,
    ForgeryResult,
    FrameScore,
    Label,
    LiveRiskState,
    RollingScoreState,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "SCHEMA_VERSION",
    "Config",
    "Label",
    "AnalysisMode",
    "LiveRiskState",
    "ForgeryResult",
    "Explanation",
    "FrameScore",
    "RollingScoreState",
]
