"""Smoke tests for the data CLI.

These do not test the pipeline — that is covered elsewhere. They test that the
entry points parse, dispatch and fail *usefully*, because a CLI that crashes
with a traceback instead of a message is the difference between a five-second
fix and an hour of confusion before a long-running job.
"""

from __future__ import annotations

import pydantic
import pytest

from falsora_ai.data.cli import main


class TestArgumentParsing:
    def test_no_command_exits(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit):
            main([])

    def test_unknown_command_exits(self) -> None:
        with pytest.raises(SystemExit):
            main(["nonsense"])

    def test_help_lists_every_subcommand(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit):
            main(["--help"])
        out = capsys.readouterr().out
        for command in ("manifest", "extract", "report", "doctor"):
            assert command in out

    def test_extract_rejects_an_invalid_split(self) -> None:
        with pytest.raises(SystemExit):
            main(["extract", "--split", "nope"])


class TestDoctor:
    def test_runs_and_returns_a_status_code(self, capsys: pytest.CaptureFixture) -> None:
        code = main(["doctor"])
        assert code in (0, 1)

    def test_reports_the_interpreter_and_dependencies(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """The interpreter path is the single most useful line: nearly every
        environment failure here is the wrong Python being active."""
        main(["doctor"])
        out = capsys.readouterr().out
        for label in ("python", "pydantic", "numpy", "opencv", "torch", "raw_datasets"):
            assert label in out

    def test_never_raises_when_dependencies_are_absent(self) -> None:
        """Doctor's whole job is to report breakage, so it must not itself break
        on the machines that need it most."""
        main(["doctor"])


class TestEnvironmentContract:
    def test_pydantic_is_v2(self) -> None:
        """contracts.py uses ConfigDict, computed_field and model_validator,
        none of which exist in pydantic v1. The guard in contracts.py turns a
        cryptic ImportError into an actionable message; this pins the
        requirement so it cannot drift silently.
        """
        assert pydantic.VERSION.split(".")[0] == "2", (
            f"pydantic {pydantic.VERSION} found; falsora requires 2.x"
        )
