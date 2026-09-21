"""
Live (WebSocket) prediction adapter — module M9.
======================================================

**Single entry point for Ujala's WebSocket per-frame path** (modules
6.13/6.14). Runs the quantized EfficientNet-B0 ONNX INT8 model — the live
path scope section 5.1 specifically mandates — and returns one
:class:`~falsora_ai.contracts.FrameScore` per frame.

Uses ``onnxruntime``, not PyTorch: this is the whole point of M7. Measured on
this project's hardware, onnx_int8 runs at ~6.5 ms/frame mean vs ~33.5 ms for
the PyTorch fp32 model doing the same job (see
``falsora_ai/optimization/benchmark.py``) — the difference between comfortably
keeping up with a 1 fps capture rate (scope 5.1 Stage 1) and not.

**Scope boundary — read before wiring this into a session:** this module
produces exactly one ``FrameScore``, stateless, no memory of prior frames.
It does **not** own the 5-frame rolling buffer, HIGH-RISK alerting, or
evidence capture — that is module 6.16's ``RollingScoreEngine``
(``falsora_ai/engine_616/rolling.py``), whose own docstring says a session's
lifecycle belongs to module 6.13 (Ujala), not to this adapter. The intended
call shape per WebSocket connection:

    predictor = FramePredictor()                    # once per process
    rolling = RollingScoreEngine(session_id=sid)     # once per session
    ...
    for frame_bytes in incoming_frames:
        score = predictor.predict(frame_bytes, session_id=sid, frame_index=i)
        if isinstance(score, EngineError):
            ...                                       # surface / skip
        else:
            state = rolling.push(score)                # -> RollingScoreState
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from falsora_ai.common.faces import FaceDetector, MTCNNDetector, crop_face
from falsora_ai.common.logging import get_logger
from falsora_ai.config import Config
from falsora_ai.contracts import EngineError, FrameScore
from falsora_ai.data.transforms import deepfake_transforms
from falsora_ai.optimization.export_onnx import onnx_path
from falsora_ai.optimization.quantize import int8_path

__all__ = ["FramePredictor", "decode_frame"]

logger = get_logger(__name__)

# When no face is detected, there is no forgery signal to report at all.
# 0.5 (maximally uncertain, authenticity 0.5) is reported rather than
# guessing a direction — see FramePredictor.predict's docstring for why
# callers should generally not feed these into RollingScoreEngine as-is.
_NO_FACE_PROBABILITY_FAKE = 0.5


def decode_frame(frame_bytes: bytes) -> np.ndarray:
    """Raw per-frame bytes (JPEG from a WebRTC/WebSocket capture, module
    6.14) -> RGB ``uint8`` ``np.ndarray``. Same convention as
    ``predict_static.decode_image``.

    Raises:
        ValueError: ``frame_bytes`` does not decode to an image.
    """
    import cv2  # local: keeps this module importable without OpenCV

    buffer = np.frombuffer(frame_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Could not decode frame bytes — corrupt frame or unsupported format.")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


class FramePredictor:
    """Process-lifetime adapter over the quantized ONNX live model for
    Ujala's per-frame WebSocket path.

    Owns one ``onnxruntime.InferenceSession`` and one face detector,
    constructed once and reused across every session and every frame —
    reloading either per frame would erase the entire latency advantage M7
    measured. Stateless otherwise: safe to share across concurrently active
    WebSocket sessions, unlike ``RollingScoreEngine``.

    Args:
        cfg: Resolves the ONNX model path and input size. Defaults to a
            fresh :class:`~falsora_ai.config.Config`.
        face_detector: Defaults to :class:`~falsora_ai.common.faces.MTCNNDetector`
            on CPU — the live path's scope target is CPU inference throughout.
            Inject a stub for tests, same convention as ``ForgeryEngine``.
        session: Pre-built ``onnxruntime.InferenceSession``, e.g. for tests
            against a tiny exported/quantized model. Defaults to loading the
            real INT8 model at :func:`int8_path` of :func:`onnx_path`.

    Raises:
        FileNotFoundError: ``session`` was not supplied and no INT8 ONNX
            model is on disk yet. Run
            ``python -m falsora_ai.optimization export`` then
            ``python -m falsora_ai.optimization quantize`` once per
            deployment before constructing this class.
    """

    def __init__(
        self,
        cfg: Config | None = None,
        face_detector: FaceDetector | None = None,
        session: Any | None = None,
    ) -> None:
        self.cfg = cfg or Config()
        self.face_detector = face_detector or MTCNNDetector(self.cfg.face, device="cpu")

        self.session = session or self._load_session()
        self.input_name = self.session.get_inputs()[0].name
        self.input_size = self.cfg.model.resolved_input_size()
        self._transform = deepfake_transforms(self.cfg, split="test")

    def _load_session(self) -> Any:
        import onnxruntime as ort

        fp32 = onnx_path(self.cfg)
        int8 = int8_path(fp32)
        if not int8.exists():
            raise FileNotFoundError(
                f"No INT8 ONNX model at {int8} — run "
                "`python -m falsora_ai.optimization export` then "
                "`python -m falsora_ai.optimization quantize` first."
            )
        return ort.InferenceSession(str(int8), providers=["CPUExecutionProvider"])

    def predict(
        self,
        frame_bytes: bytes,
        session_id: str,
        frame_index: int,
        quality_ok: bool = True,
    ) -> FrameScore | EngineError:
        """Score one live frame.

        Args:
            frame_bytes: Raw frame bytes, already sampled to the scope's
                1 fps capture rate by the WebSocket layer — this method does
                no rate limiting itself.
            session_id: Live session UUID from module 6.13. Passed straight
                through to ``FrameScore.session_id``.
            frame_index: Monotonic index within the session, owned by the
                caller (this adapter is stateless and does not count frames).
            quality_ok: Module 6.15's (Mehreen) stream-quality verdict for
                this frame, if available. Defaults True; forward whatever
                6.15 reports so ``RollingScoreEngine`` can down-weight it.

        Returns:
            A ``FrameScore`` on success, or an ``EngineError`` if the frame
            itself was undecodable — never raises. When decoding succeeds but
            no face is found, still returns a ``FrameScore`` with
            ``face_detected=False`` and ``probability_fake=0.5`` (maximally
            uncertain — there is no signal to report a direction from).
            Feeding a no-face frame into ``RollingScoreEngine`` as-is will
            pull the rolling average toward 0.5 with full weight, since
            ``rolling.py`` only discounts on ``quality_ok``, not
            ``face_detected``; callers who want no-face frames excluded
            entirely, rather than counted as neutral, should skip pushing
            them or set ``quality_ok=False`` before calling ``rolling.push``.
        """
        t0 = time.perf_counter()

        try:
            image = decode_frame(frame_bytes)
        except ValueError as exc:
            return EngineError(
                code="decode_failed",
                message=str(exc),
                module="6.6",
                recoverable=True,
                context={"session_id": session_id, "frame_index": frame_index},
            )

        try:
            box = self.face_detector.detect_batch([image])[0]
            if box is None:
                return FrameScore(
                    session_id=session_id,
                    frame_index=frame_index,
                    probability_fake=_NO_FACE_PROBABILITY_FAKE,
                    face_detected=False,
                    quality_ok=quality_ok,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )

            crop = crop_face(image, box, self.cfg.face)
            tensor = self._transform(image=crop)["image"].unsqueeze(0).numpy()
            (logit,) = self.session.run(None, {self.input_name: tensor})
            probability_fake = float(1.0 / (1.0 + np.exp(-float(logit.reshape(-1)[0]))))
        except Exception as exc:  # noqa: BLE001 — this boundary must not raise, see module docstring
            logger.exception(
                "Live inference failed for session_id=%s frame_index=%s", session_id, frame_index
            )
            return EngineError(
                code="inference_failed",
                message=str(exc),
                module="6.6",
                recoverable=False,
                context={"session_id": session_id, "frame_index": frame_index},
            )

        return FrameScore(
            session_id=session_id,
            frame_index=frame_index,
            probability_fake=probability_fake,
            face_detected=True,
            quality_ok=quality_ok,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
