"""Smoke tests for the data CLI.

These do not test the pipeline — that is covered elsewhere. They test that the
entry points parse, dispatch and fail *usefully*, because a CLI that crashes
with a traceback instead of a message is the difference between a five-second
fix and an hour of confusion before a long-running job.
"""

from __future__ import annotations

import pydantic
import pytest

from falsora_ai.data.cli import main, stratified_sample
from falsora_ai.data.manifest import VideoRecord


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


class TestStratifiedSample:
    """The smoke-test sampler.

    ``--limit`` used to truncate the manifest, which is sorted by path. The
    first 20 rows are all Celeb-DF real videos: one label, one domain, and a
    domain held out of training. A smoke test that only ever sees real faces
    from one dataset cannot detect the failure it exists to detect, namely a
    detector that loses fakes more often than reals and quietly reweights the
    classes. These tests pin the fix.
    """

    @staticmethod
    def corpus() -> list[VideoRecord]:
        out = []
        for domain, label, n in [
            ("celebdf", "real", 50),
            ("celebdf", "fake", 50),
            ("ffpp", "real", 50),
            ("ffpp", "fake", 50),
            ("dfd", "real", 4),  # deliberately smaller than the round-robin quota
        ]:
            for i in range(n):
                out.append(
                    VideoRecord(
                        relpath=f"{domain}/{label}/{i:04d}.mp4",
                        source=f"{domain}/{label}",
                        domain=domain,
                        label=label,
                        role="train_pool",
                        identities=(f"{domain}:{i}",),
                        frames=8,
                    )
                )
        return sorted(out, key=lambda r: r.relpath)

    def test_covers_every_stratum(self) -> None:
        sample = stratified_sample(self.corpus(), 20, seed=1337)
        strata = {(r.domain, r.label) for r in sample}
        assert strata == {
            ("celebdf", "real"),
            ("celebdf", "fake"),
            ("ffpp", "real"),
            ("ffpp", "fake"),
            ("dfd", "real"),
        }

    def test_prefix_truncation_would_not_have(self) -> None:
        """The bug this replaced, stated as an assertion so it cannot return."""
        prefix = self.corpus()[:20]
        assert len({(r.domain, r.label) for r in prefix}) == 1

    def test_returns_exactly_n(self) -> None:
        assert len(stratified_sample(self.corpus(), 20, seed=1337)) == 20

    def test_is_deterministic_for_a_seed(self) -> None:
        a = stratified_sample(self.corpus(), 25, seed=1337)
        b = stratified_sample(self.corpus(), 25, seed=1337)
        assert [r.relpath for r in a] == [r.relpath for r in b]

    def test_drains_small_strata_without_looping_forever(self) -> None:
        """dfd/real has 4 videos; asking for 25 must not spin or duplicate."""
        sample = stratified_sample(self.corpus(), 25, seed=1337)
        assert len(sample) == 25
        assert len({r.relpath for r in sample}) == 25
        assert sum(r.domain == "dfd" for r in sample) == 4

    def test_n_larger_than_corpus_returns_everything_once(self) -> None:
        corpus = self.corpus()
        sample = stratified_sample(corpus, 10_000, seed=1337)
        assert len(sample) == len(corpus)
        assert {r.relpath for r in sample} == {r.relpath for r in corpus}

    def test_preserves_manifest_order(self) -> None:
        corpus = self.corpus()
        order = {r.relpath: i for i, r in enumerate(corpus)}
        sample = stratified_sample(corpus, 30, seed=1337)
        assert [order[r.relpath] for r in sample] == sorted(
            order[r.relpath] for r in sample
        )

    def test_zero_and_negative_are_empty(self) -> None:
        assert stratified_sample(self.corpus(), 0, seed=1) == []
        assert stratified_sample(self.corpus(), -5, seed=1) == []
