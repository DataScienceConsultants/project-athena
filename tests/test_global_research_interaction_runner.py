import csv
import json
from datetime import UTC, datetime

from src.catalog.models import CatalogEvent
from src.global_research.models import GlobalResearchProfile
from src.global_research.runner import run_global_research


def test_runner_persists_cited_interaction_study_artifacts(tmp_path):
    profile = GlobalResearchProfile(
        profile_id="interaction-fixture",
        start_time=datetime(2020, 1, 1, tzinfo=UTC),
        end_time=datetime(2020, 2, 1, tzinfo=UTC),
        minimum_magnitude=6.0,
    )

    events = (
        CatalogEvent(
            event_id="pre",
            time=datetime(2020, 1, 9, tzinfo=UTC),
            latitude=0.0,
            longitude=0.5,
            depth=10.0,
            magnitude=6.2,
            magnitude_type="mww",
            source="USGS",
        ),
        CatalogEvent(
            event_id="source",
            time=datetime(2020, 1, 10, tzinfo=UTC),
            latitude=0.0,
            longitude=0.6,
            depth=12.0,
            magnitude=7.1,
            magnitude_type="mww",
            source="USGS",
        ),
        CatalogEvent(
            event_id="post",
            time=datetime(2020, 1, 11, tzinfo=UTC),
            latitude=0.0,
            longitude=0.7,
            depth=8.0,
            magnitude=6.4,
            magnitude_type="mb",
            source="USGS",
        ),
    )

    class FakeDownloader:
        def download(self, query):
            return events

    plate_path = tmp_path / "PB2002_steps.dat.txt"
    plate_path.write_text(
        "   1  AA-BB    0.000 0.000    2.000 0.000  222.0 90  10.0 90 "
        "  2.0   8.0 -3000 10  SUB\n",
        encoding="utf-8",
    )

    output = tmp_path / "bundle"
    result = run_global_research(
        profile=profile,
        output_dir=output,
        plate_boundary_steps_path=plate_path,
        max_plate_boundary_distance_km=100.0,
        interaction_study=True,
        interaction_max_lag_days=30.0,
        interaction_max_distance_km=500.0,
        interaction_time_windows_days=(1.0, 7.0),
        interaction_distance_windows_km=(100.0, 500.0),
        counter=lambda query: 3,
        downloader=FakeDownloader(),
        generated_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
    )

    assert result.metadata["bundle_schema_version"] == 3
    assert result.metadata["interaction_study_included"] is True
    assert result.metadata["interaction_pair_count"] == 3
    assert result.metadata["interaction_window_observation_count"] == 12
    assert result.metadata["interaction_inference_status"] == (
        "descriptive_only_no_independence_assumption"
    )
    assert "no causal triggering" in result.metadata["interaction_semantics"]

    for name in (
        "interaction_pairs.csv",
        "interaction_windows.csv",
        "interaction_summary.json",
    ):
        assert (output / name).is_file()

    summary = json.loads(
        (output / "interaction_summary.json").read_text(encoding="utf-8")
    )
    assert summary["study_id"] == "global-m6-1976-2025-interaction-v1"
    assert summary["report_is_nonpredictive"] is True
    assert summary["pair_count"] == 3
    assert len(summary["limitations"]) >= 5
    citation_keys = {item["source_key"] for item in summary["source_citations"]}
    assert citation_keys == {
        "usgs_magnitude_types",
        "hanks_kanamori_1979",
        "dieterich_1994",
        "king_stein_lin_1994",
        "brodsky_prejean_2005",
    }

    with (output / "interaction_pairs.csv").open(
        "r", encoding="utf-8", newline=""
    ) as source:
        rows = list(csv.DictReader(source))
    source_post = next(
        row
        for row in rows
        if row["source_event_id"] == "source" and row["target_event_id"] == "post"
    )
    assert source_post["same_plate_pair"] == "True"
    assert source_post["source_moment_nm"]
    assert source_post["target_moment_nm"] == ""
