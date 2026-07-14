"""Tests for the Project Athena command-line interface."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.cli as cli


def test_parser_requires_a_command() -> None:
    """Athena should reject a command line without a subcommand."""

    parser = cli.build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([])

    assert exc_info.value.code == 2


def test_observatory_arguments_are_parsed() -> None:
    """Observatory CLI options should be parsed correctly."""

    parser = cli.build_parser()

    arguments = parser.parse_args(
        [
            "observatory",
            "--catalog",
            "data/processed/catalog.parquet",
            "--region",
            "puerto_rico",
            "--output",
            "outputs/reports/report.json",
        ]
    )

    assert arguments.command == "observatory"
    assert arguments.catalog == Path(
        "data/processed/catalog.parquet"
    )
    assert arguments.region == "puerto_rico"
    assert arguments.output == Path(
        "outputs/reports/report.json"
    )


def test_observatory_command_calls_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI should pass Observatory options to the report runner."""

    received: dict[str, object] = {}

    def fake_run_report(
        *,
        catalog_path: Path | None = None,
        region_key: str | None = None,
        output_path: Path | None = None,
    ) -> tuple[object, Path]:
        received["catalog_path"] = catalog_path
        received["region_key"] = region_key
        received["output_path"] = output_path

        return object(), Path("report.json")

    monkeypatch.setattr(
        cli,
        "run_report",
        fake_run_report,
    )

    result = cli.main(
        [
            "observatory",
            "--catalog",
            "catalog.parquet",
            "--region",
            "puerto_rico",
            "--output",
            "report.json",
        ]
    )

    assert result == 0
    assert received == {
        "catalog_path": Path("catalog.parquet"),
        "region_key": "puerto_rico",
        "output_path": Path("report.json"),
    }


def test_observatory_uses_default_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitted Observatory options should remain unset."""

    received: dict[str, object] = {}

    def fake_run_report(
        *,
        catalog_path: Path | None = None,
        region_key: str | None = None,
        output_path: Path | None = None,
    ) -> tuple[object, Path]:
        received["catalog_path"] = catalog_path
        received["region_key"] = region_key
        received["output_path"] = output_path

        return object(), Path("report.json")

    monkeypatch.setattr(
        cli,
        "run_report",
        fake_run_report,
    )

    result = cli.main(["observatory"])

    assert result == 0
    assert received == {
        "catalog_path": None,
        "region_key": None,
        "output_path": None,
    }


def test_cli_returns_failure_for_missing_catalog(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Expected operational errors should return a nonzero status."""

    def fake_run_report(
        *,
        catalog_path: Path | None = None,
        region_key: str | None = None,
        output_path: Path | None = None,
    ) -> tuple[object, Path]:
        del catalog_path, region_key, output_path

        raise FileNotFoundError(
            "No earthquake catalog was found."
        )

    monkeypatch.setattr(
        cli,
        "run_report",
        fake_run_report,
    )

    result = cli.main(["observatory"])

    assert result == 1
    assert "No earthquake catalog was found." in caplog.text


def test_verbose_flag_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The global verbose option should work before the subcommand."""

    monkeypatch.setattr(
        cli,
        "run_report",
        lambda **_: (object(), Path("report.json")),
    )

    result = cli.main(
        [
            "--verbose",
            "observatory",
        ]
    )

    assert result == 0