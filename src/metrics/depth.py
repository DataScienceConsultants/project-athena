"""Earthquake depth metrics for Project Athena."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class DepthSummary:
    """Summary of earthquake depths for a selected period."""

    events_with_depth: int
    average_depth_km: float | None
    median_depth_km: float | None
    minimum_depth_km: float | None
    maximum_depth_km: float | None
    depth_standard_deviation_km: float | None
    shallow_events: int
    intermediate_events: int
    deep_events: int
    shallowest_event_id: str | None
    deepest_event_id: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return the summary as a dictionary."""

        return asdict(self)


def validate_depth_catalog(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize an event-level earthquake catalog."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Catalog must be a pandas DataFrame.")

    required_columns = {
        "event_id",
        "event_time_utc",
        "depth_km",
    }

    missing_columns = required_columns.difference(dataframe.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"Catalog is missing required columns: {missing_text}"
        )

    catalog = dataframe.copy()

    catalog["event_time_utc"] = pd.to_datetime(
        catalog["event_time_utc"],
        utc=True,
        errors="coerce",
    )

    catalog["depth_km"] = pd.to_numeric(
        catalog["depth_km"],
        errors="coerce",
    )

    catalog = catalog.dropna(
        subset=["event_id", "event_time_utc"]
    )

    source_subset = (
        ["source", "event_id"]
        if "source" in catalog.columns
        else ["event_id"]
    )

    catalog = catalog.drop_duplicates(
        subset=source_subset,
        keep="last",
    )

    return catalog.sort_values(
        ["event_time_utc", "event_id"]
    ).reset_index(drop=True)


def classify_depth(depth_km: float | int | None) -> str | None:
    """Classify an earthquake using broad depth categories.

    Categories:
        shallow: depth below 70 km
        intermediate: 70 km through less than 300 km
        deep: 300 km or greater
    """

    if depth_km is None or pd.isna(depth_km):
        return None

    numeric_depth = float(depth_km)

    if numeric_depth < 70:
        return "shallow"

    if numeric_depth < 300:
        return "intermediate"

    return "deep"


def add_depth_categories(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Add a depth-category column to an earthquake catalog."""

    catalog = validate_depth_catalog(dataframe)

    catalog["depth_category"] = catalog["depth_km"].map(
        classify_depth
    )

    return catalog


def build_daily_depth(
    dataframe: pd.DataFrame,
    *,
    include_inactive_days: bool = True,
) -> pd.DataFrame:
    """Aggregate earthquake depth metrics by UTC calendar day."""

    catalog = add_depth_categories(dataframe)

    output_columns = [
        "date",
        "event_count",
        "events_with_depth",
        "average_depth_km",
        "median_depth_km",
        "minimum_depth_km",
        "maximum_depth_km",
        "depth_standard_deviation_km",
        "shallow_events",
        "intermediate_events",
        "deep_events",
    ]

    if catalog.empty:
        return pd.DataFrame(columns=output_columns)

    catalog["date"] = (
        catalog["event_time_utc"]
        .dt.tz_convert("UTC")
        .dt.floor("D")
        .dt.tz_localize(None)
    )

    catalog["is_shallow"] = (
        catalog["depth_category"] == "shallow"
    )
    catalog["is_intermediate"] = (
        catalog["depth_category"] == "intermediate"
    )
    catalog["is_deep"] = (
        catalog["depth_category"] == "deep"
    )

    daily = (
        catalog.groupby("date", as_index=False)
        .agg(
            event_count=("event_id", "count"),
            events_with_depth=("depth_km", "count"),
            average_depth_km=("depth_km", "mean"),
            median_depth_km=("depth_km", "median"),
            minimum_depth_km=("depth_km", "min"),
            maximum_depth_km=("depth_km", "max"),
            depth_standard_deviation_km=("depth_km", "std"),
            shallow_events=("is_shallow", "sum"),
            intermediate_events=("is_intermediate", "sum"),
            deep_events=("is_deep", "sum"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    count_columns = [
        "event_count",
        "events_with_depth",
        "shallow_events",
        "intermediate_events",
        "deep_events",
    ]

    daily[count_columns] = daily[count_columns].astype("int64")

    if include_inactive_days:
        complete_dates = pd.DataFrame(
            {
                "date": pd.date_range(
                    start=daily["date"].min(),
                    end=daily["date"].max(),
                    freq="D",
                )
            }
        )

        daily = complete_dates.merge(
            daily,
            on="date",
            how="left",
        )

        daily[count_columns] = (
            daily[count_columns]
            .fillna(0)
            .astype("int64")
        )

    decimal_columns = [
        "average_depth_km",
        "median_depth_km",
        "minimum_depth_km",
        "maximum_depth_km",
        "depth_standard_deviation_km",
    ]

    daily[decimal_columns] = daily[decimal_columns].round(3)

    return daily[output_columns]


def add_rolling_depth_metrics(
    daily_depth: pd.DataFrame,
) -> pd.DataFrame:
    """Add rolling and historical depth comparisons."""

    required_columns = {
        "date",
        "average_depth_km",
    }

    missing_columns = required_columns.difference(
        daily_depth.columns
    )

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            "Daily depth data is missing required columns: "
            f"{missing_text}"
        )

    metrics = daily_depth.copy()

    metrics["date"] = pd.to_datetime(
        metrics["date"],
        errors="coerce",
    )

    metrics["average_depth_km"] = pd.to_numeric(
        metrics["average_depth_km"],
        errors="coerce",
    )

    metrics = (
        metrics.dropna(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    depth = metrics["average_depth_km"]

    metrics["average_depth_7d_km"] = depth.rolling(
        window=7,
        min_periods=1,
    ).mean()

    metrics["average_depth_30d_km"] = depth.rolling(
        window=30,
        min_periods=1,
    ).mean()

    metrics["historical_expanding_depth_average_km"] = (
        depth.expanding(min_periods=1)
        .mean()
        .shift(1)
    )

    historical_average = metrics[
        "historical_expanding_depth_average_km"
    ]

    metrics["depth_difference_7d_km"] = (
        metrics["average_depth_7d_km"]
        - historical_average
    )

    metrics["depth_difference_30d_km"] = (
        metrics["average_depth_30d_km"]
        - historical_average
    )

    decimal_columns = [
        "average_depth_7d_km",
        "average_depth_30d_km",
        "historical_expanding_depth_average_km",
        "depth_difference_7d_km",
        "depth_difference_30d_km",
    ]

    metrics[decimal_columns] = metrics[decimal_columns].round(4)

    return metrics


def summarize_depth(
    dataframe: pd.DataFrame,
) -> DepthSummary:
    """Create a period-level depth summary."""

    catalog = add_depth_categories(dataframe)

    usable = catalog.dropna(subset=["depth_km"])

    if usable.empty:
        return DepthSummary(
            events_with_depth=0,
            average_depth_km=None,
            median_depth_km=None,
            minimum_depth_km=None,
            maximum_depth_km=None,
            depth_standard_deviation_km=None,
            shallow_events=0,
            intermediate_events=0,
            deep_events=0,
            shallowest_event_id=None,
            deepest_event_id=None,
        )

    shallowest_index = usable["depth_km"].idxmin()
    deepest_index = usable["depth_km"].idxmax()

    standard_deviation = usable["depth_km"].std()

    return DepthSummary(
        events_with_depth=int(len(usable)),
        average_depth_km=round(
            float(usable["depth_km"].mean()),
            3,
        ),
        median_depth_km=round(
            float(usable["depth_km"].median()),
            3,
        ),
        minimum_depth_km=round(
            float(usable["depth_km"].min()),
            3,
        ),
        maximum_depth_km=round(
            float(usable["depth_km"].max()),
            3,
        ),
        depth_standard_deviation_km=(
            round(float(standard_deviation), 3)
            if pd.notna(standard_deviation)
            else None
        ),
        shallow_events=int(
            usable["depth_category"].eq("shallow").sum()
        ),
        intermediate_events=int(
            usable["depth_category"].eq("intermediate").sum()
        ),
        deep_events=int(
            usable["depth_category"].eq("deep").sum()
        ),
        shallowest_event_id=str(
            usable.loc[shallowest_index, "event_id"]
        ),
        deepest_event_id=str(
            usable.loc[deepest_index, "event_id"]
        ),
    )