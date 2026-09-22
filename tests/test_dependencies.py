"""Tests that the declared dependency constraints are internally coherent.

These exist because of a real failure. ``numpy>=1.26`` with ``torch<2.6``
installed cleanly, passed every import check, and then died several minutes
into a multi-hour extraction with::

    RuntimeError: Could not infer dtype of numpy.uint8

raised deep inside MTCNN. torch wheels below 2.6 are compiled against the
numpy 1.x C API; under numpy 2.x torch imports with a warning rather than an
error, so nothing fails until the first ndarray actually crosses into torch.

A constraint that is only enforced by someone remembering it is not enforced.
The pins are parsed straight out of ``pyproject.toml`` here so that loosening
one turns a silent, delayed, hard-to-attribute runtime crash into a failing
test at commit time.

``tomllib`` is 3.11+, and this project supports 3.10, so the file is parsed
with a small regex instead of taking a dependency for one test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def ml_requirements() -> dict[str, str]:
    """Map package name → version specifier from the ``[ml]`` extra."""
    text = PYPROJECT.read_text(encoding="utf-8")
    block = re.search(r"^ml = \[(.*?)^\]", text, re.MULTILINE | re.DOTALL)
    assert block, "Could not locate the [ml] extra in pyproject.toml"

    out: dict[str, str] = {}
    for entry in re.findall(r'"([^"]+)"', block.group(1)):
        name = re.split(r"[><=!~\[]", entry, maxsplit=1)[0].strip()
        out[name.lower()] = entry[len(name) :].strip()
    return out


@pytest.fixture(scope="module")
def requirements() -> dict[str, str]:
    return ml_requirements()


class TestPinsParse:
    def test_the_ml_extra_is_readable(self, requirements: dict[str, str]) -> None:
        assert "torch" in requirements
        assert "numpy" in requirements


class TestNumpyTorchCompatibility:
    """The pin that caused a real, hours-long failure."""

    def test_numpy_is_capped_below_2(self, requirements: dict[str, str]) -> None:
        assert "<2" in requirements["numpy"], (
            "numpy must stay below 2.x while torch is pinned below 2.6: torch "
            "wheels in that range are built against the numpy 1.x C API. The "
            "failure is delayed and appears inside MTCNN, not at import."
        )

    def test_torch_is_capped_below_2_6(self, requirements: dict[str, str]) -> None:
        """facenet-pytorch's pretrained weights fail to load under torch 2.6+,
        which changed ``torch.load`` to default ``weights_only=True``."""
        assert "<2.6" in requirements["torch"]

    def test_raising_numpy_requires_raising_torch(
        self, requirements: dict[str, str]
    ) -> None:
        """The two pins are one decision, not two.

        Whoever eventually lifts numpy past 2.x must also move torch to >=2.6
        and deal with facenet-pytorch. Encoding the implication here means the
        pins cannot drift apart one commit at a time.
        """
        numpy_capped = "<2" in requirements["numpy"]
        torch_capped = "<2.6" in requirements["torch"]
        assert numpy_capped == torch_capped, (
            "numpy<2 and torch<2.6 must be lifted together. Lifting numpy alone "
            "breaks the torch C API; lifting torch alone breaks facenet-pytorch."
        )


class TestOpenCVCompatibility:
    def test_opencv_is_capped_below_5(self, requirements: dict[str, str]) -> None:
        """OpenCV 5.x requires numpy>=2, which contradicts the numpy cap."""
        assert "<5" in requirements["opencv-python-headless"]

    def test_only_the_headless_variant_is_declared(
        self, requirements: dict[str, str]
    ) -> None:
        """``opencv-python`` and ``opencv-python-headless`` install the same
        ``cv2`` package. Declaring both leaves whichever was installed last
        shadowing the other, with no error and no way to tell which is live.
        Nothing in this pipeline needs the GUI build.
        """
        assert "opencv-python" not in requirements


class TestCoreStaysLightweight:
    def test_torch_is_not_a_core_dependency(self) -> None:
        """Ujala's API and Mehreen's decision engine import contracts.py. If
        torch leaked into the core dependency list, a 2 GB download would
        become mandatory for a module that only needs pydantic models.
        """
        text = PYPROJECT.read_text(encoding="utf-8")
        core = re.search(
            r"^dependencies = \[(.*?)^\]", text, re.MULTILINE | re.DOTALL
        )
        assert core, "Could not locate core dependencies in pyproject.toml"
        for heavy in ("torch", "opencv", "timm", "numpy"):
            assert heavy not in core.group(1).lower(), (
                f"{heavy} must stay in an optional extra, not core dependencies"
            )
