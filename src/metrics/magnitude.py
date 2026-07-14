"""Earthquake magnitude metrics for Project Athena.

This module calculates event-level, daily, rolling, and period-level
magnitude statistics. It contains no display or forecasting logic so the
same calculations can be reused by reports, dashboards, APIs, and models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


REQUIRED_MAGNITUDE_COLUMNS = {
    "event_id",
    "event_time_utc",
    "magnitude",
}


@dataclass(frozen=True, slots=True)
class MagnitudeSummary:
    """Summary of earthquake magnitudes over a selected period."""

    total_events: int
    events_with_magnitude: int
    missing_magnitude_count: int
    average_magnitude: float | None
    median_magnitude: float | None
    minimum_magnitude: float | None
    maximum_magnitude: float | None
    magnitude_standard_deviation: float | None
    magnitude_1_plus: int
    magnitude_2_plus: int
    magnitude_3_plus: int
    magnitude_4_plus: int
    magnitude_5_plus: int
    largest_event_id: str | None
    largest_event_time_utc: str | None
    largest_event_place: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return the summary as a dictionary."""

        return asdict(self)


def validate_magnitude_catalog(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Validate and normalize an event-level earthquake catalog.

    Args:
        dataframe: Event-level earthquake catalog.

    Returns:
        A cleaned, deduplicated, chronologically sorted DataFrame.

    Raises:
        TypeError: When the input is not a pandas DataFrame.
        ValueError: When required columns are missing.
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Catalog must be a pandas DataFrame.")

    missing_columns = REQUIRED_MAGNITUDE_COLUMNS.difference(
        dataframe.columns
    )

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

    catalog["magnitude"] = pd.to_numeric(
        catalog["magnitude"],
        errors="coerce",
    )

    catalog = catalog.dropna(
        subset=[
            "event_id",
            "event_time_utc",
        ]
    )

    duplicate_columns = (
        ["source", "event_id"]
        if "source" in catalog.columns
        else ["event_id"]
    )

    catalog = catalog.drop_duplicates(
        subset=duplicate_columns,
        keep="last",
    )

    return catalog.sort_values(
        ["event_time_utc", "event_id"]
    ).reset_index(drop=True)


def add_magnitude_categories(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Add magnitude-band and threshold columns to a catalog.

    Added columns:

        magnitude_band
        magnitude_1_plus
        magnitude_2_plus
        magnitude_3_plus
        magnitude_4_plus
        magnitude_5_plus

    Magnitude bands:

        below_1
        1_to_1_9
        2_to_2_9
        3_to_3_9
        4_to_4_9
        5_plus
        unavailable
    """

    catalog = validate_magnitude_catalog(dataframe)

    catalog["magnitude_band"] = catalog["magnitude"].map(
        classify_magnitude_band
    )

    thresholds = {
        "magnitude_1_plus": 1.0,
        "magnitude_2_plus": 2.0,
        "magnitude_3_plus": 3.0,
        "magnitude_4_plus": 4.0,
        "magnitude_5_plus": 5.0,
    }

    for column, threshold in thresholds.items():
        catalog[column] = (
            catalog["magnitude"]
            .ge(threshold)
            .fillna(False)
        )

    return catalog


def classify_magnitude_band(
    magnitude: float | int | None,
) -> str:
    """Return Athena's descriptive magnitude band."""

    if magnitude is None or pd.isna(magnitude):
        return "unavailable"

    numeric_magnitude = float(magnitude)

    if numeric_magnitude < 1.0:
        return "below_1"

    if numeric_magnitude < 2.0:
        return "1_to_1_9"

    if numeric_magnitude < 3.0:
        return "2_to_2_9"

    if numeric_magnitude < 4.0:
        return "3_to_3_9"

    if numeric_magnitude < 5.0:
        return "4_to_4_9"

    return "5_plus"


def build_daily_magnitude(
    dataframe: pd.DataFrame,
    *,
    include_inactive_days: bool = True,
) -> pd.DataFrame:
    """Aggregate magnitude metrics into one row per UTC day.

    Output columns:

        date
        event_count
        events_with_magnitude
        missing_magnitude_count
        average_magnitude
        median_magnitude
        minimum_magnitude
        maximum_magnitude
        magnitude_standard_deviation
        magnitude_1_plus
        magnitude_2_plus
        magnitude_3_plus
        magnitude_4_plus
        magnitude_5_plus
    """

    catalog = add_magnitude_categories(dataframe)

    output_columns = [
        "date",
        "event_count",
        "events_with_magnitude",
        "missing_magnitude_count",
        "average_magnitude",
        "median_magnitude",
        "minimum_magnitude",
        "maximum_magnitude",
        "magnitude_standard_deviation",
        "magnitude_1_plus",
        "magnitude_2_plus",
        "magnitude_3_plus",
        "magnitude_4_plus",
        "magnitude_5_plus",
    ]

    if catalog.empty:
        return pd.DataFrame(columns=output_columns)

    catalog["date"] = (
        catalog["event_time_utc"]
        .dt.tz_convert("UTC")
        .dt.floor("D")
        .dt.tz_localize(None)
    )

    daily = (
        catalog.groupby("date", as_index=False)
        .agg(
            event_count=("event_id", "count"),
            events_with_magnitude=("magnitude", "count"),
            average_magnitude=("magnitude", "mean"),
            median_magnitude=("magnitude", "median"),
            minimum_magnitude=("magnitude", "min"),
            maximum_magnitude=("magnitude", "max"),
            magnitude_standard_deviation=("magnitude", "std"),
            magnitude_1_plus=("magnitude_1_plus", "sum"),
            magnitude_2_plus=("magnitude_2_plus", "sum"),
            magnitude_3_plus=("magnitude_3_plus", "sum"),
            magnitude_4_plus=("magnitude_4_plus", "sum"),
            magnitude_5_plus=("magnitude_5_plus", "sum"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    daily["missing_magnitude_count"] = (
        daily["event_count"]
        - daily["events_with_magnitude"]
    )

    count_columns = [
        "event_count",
        "events_with_magnitude",
        "missing_magnitude_count",
        "magnitude_1_plus",
        "magnitude_2_plus",
        "magnitude_3_plus",
        "magnitude_4_plus",
        "magnitude_5_plus",
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
        "average_magnitude",
        "median_magnitude",
        "minimum_magnitude",
        "maximum_magnitude",
        "magnitude_standard_deviation",
    ]

    daily[decimal_columns] = daily[decimal_columns].round(4)

    return daily[output_columns]


def add_rolling_magnitude_metrics(
    daily_magnitude: pd.DataFrame,
) -> pd.DataFrame:
    """Add rolling and historical magnitude comparisons.

    Added columns:

        average_magnitude_7d
        average_magnitude_30d
        maximum_magnitude_7d
        maximum_magnitude_30d
        historical_expanding_average_magnitude
        average_magnitude_difference_7d
        average_magnitude_difference_30d

    Historical expanding values are shifted by one day to prevent
    future-data leakage.
    """

    required_columns = {
        "date",
        "average_magnitude",
        "maximum_magnitude",
    }

    missing_columns = required_columns.difference(
        daily_magnitude.columns
    )

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            "Daily magnitude data is missing required columns: "
            f"{missing_text}"
        )

    metrics = daily_magnitude.copy()

    metrics["date"] = pd.to_datetime(
        metrics["date"],
        errors="coerce",
    )

    metrics["average_magnitude"] = pd.to_numeric(
        metrics["average_magnitude"],
        errors="coerce",
    )

    metrics["maximum_magnitude"] = pd.to_numeric(
        metrics["maximum_magnitude"],
        errors="coerce",
    )

    metrics = (
        metrics.dropna(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    average_magnitude = metrics["average_magnitude"]
    maximum_magnitude = metrics["maximum_magnitude"]

    metrics["average_magnitude_7d"] = (
        average_magnitude
        .rolling(window=7, min_periods=1)
        .mean()
    )

    metrics["average_magnitude_30d"] = (
        average_magnitude
        .rolling(window=30, min_periods=1)
        .mean()
    )

    metrics["maximum_magnitude_7d"] = (
        maximum_magnitude
        .rolling(window=7, min_periods=1)
        .max()
    )

    metrics["maximum_magnitude_30d"] = (
        maximum_magnitude
        .rolling(window=30, min_periods=1)
        .max()
    )

    metrics[
        "historical_expanding_average_magnitude"
    ] = (
        average_magnitude
        .expanding(min_periods=1)
        .mean()
        .shift(1)
    )

    historical_average = metrics[
        "historical_expanding_average_magnitude"
    ]

    metrics["average_magnitude_difference_7d"] = (
        metrics["average_magnitude_7d"]
        - historical_average
    )

    metrics["average_magnitude_difference_30d"] = (
        metrics["average_magnitude_30d"]
        - historical_average
    )

    decimal_columns = [
        "average_magnitude_7d",
        "average_magnitude_30d",
        "maximum_magnitude_7d",
        "maximum_magnitude_30d",
        "historical_expanding_average_magnitude",
        "average_magnitude_difference_7d",
        "average_magnitude_difference_30d",
    ]

    metrics[decimal_columns] = metrics[decimal_columns].round(4)

    return metrics


def summarize_magnitude(
    dataframe: pd.DataFrame,
) -> MagnitudeSummary:
    """Create a period-level magnitude summary."""

    catalog = add_magnitude_categories(dataframe)
    usable = catalog.dropna(subset=["magnitude"])

    total_events = int(len(catalog))
    events_with_magnitude = int(len(usable))

    if usable.empty:
        return MagnitudeSummary(
            total_events=total_events,
            events_with_magnitude=0,
            missing_magnitude_count=total_events,
            average_magnitude=None,
            median_magnitude=None,
            minimum_magnitude=None,
            maximum_magnitude=None,
            magnitude_standard_deviation=None,
            magnitude_1_plus=0,
            magnitude_2_plus=0,
            magnitude_3_plus=0,
            magnitude_4_plus=0,
            magnitude_5_plus=0,
            largest_event_id=None,
            largest_event_time_utc=None,
            largest_event_place=None,
        )

    largest_index = usable["magnitude"].idxmax()
    largest_event = usable.loc[largest_index]

    standard_deviation = usable["magnitude"].std()

    place_value = (
        largest_event.get("place")
        if "place" in largest_event.index
        else None
    )

    event_time = pd.Timestamp(
        largest_event["event_time_utc"]
    )

    return MagnitudeSummary(
        total_events=total_events,
        events_with_magnitude=events_with_magnitude,
        missing_magnitude_count=(
            total_events - events_with_magnitude
        ),
        average_magnitude=round(
            float(usable["magnitude"].mean()),
            4,
        ),
        median_magnitude=round(
            float(usable["magnitude"].median()),
            4,
        ),
        minimum_magnitude=round(
            float(usable["magnitude"].min()),
            4,
        ),
        maximum_magnitude=round(
            float(usable["magnitude"].max()),
            4,
        ),
        magnitude_standard_deviation=(
            round(float(standard_deviation), 4)
            if pd.notna(standard_deviation)
            else None
        ),
        magnitude_1_plus=int(
            usable["magnitude_1_plus"].sum()
        ),
        magnitude_2_plus=int(
            usable["magnitude_2_plus"].sum()
        ),
        magnitude_3_plus=int(
            usable["magnitude_3_plus"].sum()
        ),
        magnitude_4_plus=int(
            usable["magnitude_4_plus"].sum()
        ),
        magnitude_5_plus=int(
            usable["magnitude_5_plus"].sum()
        ),
        largest_event_id=str(
            largest_event["event_id"]
        ),
        largest_event_time_utc=event_time.isoformat(),
        largest_event_place=(
            str(place_value)
            if pd.notna(place_value)
            else None
        ),
    )