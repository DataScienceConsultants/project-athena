"""Earthquake activity metrics for Project Athena.

This module converts an event-level earthquake catalog into daily activity
metrics. It contains no visualization or forecasting logic so the same
calculations can be reused by notebooks, dashboards, APIs, and models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_CATALOG_COLUMNS = {
    "event_id",
    "event_time_utc",
    "magnitude",
}


@dataclass(frozen=True, slots=True)
class ActivitySummary:
    """Summary of earthquake activity over a selected catalog period."""

    total_events: int
    active_days: int
    calendar_days: int
    average_events_per_day: float
    median_events_per_day: float
    maximum_events_in_one_day: int
    busiest_day: str | None
    magnitude_1_plus: int
    magnitude_2_plus: int
    magnitude_3_plus: int
    magnitude_4_plus: int
    magnitude_5_plus: int

    def to_dict(self) -> dict[str, Any]:
        """Return the summary as a dictionary."""

        return asdict(self)


def load_catalog(catalog_path: str | Path) -> pd.DataFrame:
    """Load a Project Athena earthquake catalog.

    Supported formats:
        - Parquet
        - CSV

    Args:
        catalog_path: Path to the saved earthquake catalog.

    Returns:
        A validated and chronologically sorted DataFrame.

    Raises:
        FileNotFoundError: When the catalog path does not exist.
        ValueError: When the file type or required columns are invalid.
    """

    path = Path(catalog_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Earthquake catalog was not found: {path}"
        )

    suffix = path.suffix.lower()

    if suffix == ".parquet":
        dataframe = pd.read_parquet(path)
    elif suffix == ".csv":
        dataframe = pd.read_csv(path)
    else:
        raise ValueError(
            "Catalog must be a Parquet or CSV file."
        )

    return validate_catalog(dataframe)


def validate_catalog(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize an event-level earthquake catalog."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Catalog must be a pandas DataFrame.")

    missing_columns = REQUIRED_CATALOG_COLUMNS.difference(
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


def build_daily_activity(
    dataframe: pd.DataFrame,
    *,
    include_inactive_days: bool = True,
) -> pd.DataFrame:
    """Aggregate event-level data into one row per UTC calendar day.

    Output columns include:

        date
        event_count
        magnitude_1_plus
        magnitude_2_plus
        magnitude_3_plus
        magnitude_4_plus
        magnitude_5_plus
        maximum_magnitude
        average_magnitude
        median_magnitude

    When ``include_inactive_days`` is true, days with zero catalog events are
    included between the first and last event dates.
    """

    catalog = validate_catalog(dataframe)

    output_columns = [
        "date",
        "event_count",
        "magnitude_1_plus",
        "magnitude_2_plus",
        "magnitude_3_plus",
        "magnitude_4_plus",
        "magnitude_5_plus",
        "maximum_magnitude",
        "average_magnitude",
        "median_magnitude",
    ]

    if catalog.empty:
        return pd.DataFrame(columns=output_columns)

    catalog["date"] = (
        catalog["event_time_utc"]
        .dt.tz_convert("UTC")
        .dt.floor("D")
        .dt.tz_localize(None)
    )

    magnitude_thresholds = {
        "magnitude_1_plus": 1.0,
        "magnitude_2_plus": 2.0,
        "magnitude_3_plus": 3.0,
        "magnitude_4_plus": 4.0,
        "magnitude_5_plus": 5.0,
    }

    for column, threshold in magnitude_thresholds.items():
        catalog[column] = (
            catalog["magnitude"].ge(threshold).fillna(False)
        )

    daily = (
        catalog.groupby("date", as_index=False)
        .agg(
            event_count=("event_id", "count"),
            magnitude_1_plus=("magnitude_1_plus", "sum"),
            magnitude_2_plus=("magnitude_2_plus", "sum"),
            magnitude_3_plus=("magnitude_3_plus", "sum"),
            magnitude_4_plus=("magnitude_4_plus", "sum"),
            magnitude_5_plus=("magnitude_5_plus", "sum"),
            maximum_magnitude=("magnitude", "max"),
            average_magnitude=("magnitude", "mean"),
            median_magnitude=("magnitude", "median"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    count_columns = [
        "event_count",
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

    return daily[output_columns]


def add_rolling_activity_metrics(
    daily_activity: pd.DataFrame,
) -> pd.DataFrame:
    """Add rolling earthquake-count metrics to daily activity data.

    Added columns:

        event_count_7d
        event_count_30d
        daily_average_7d
        daily_average_30d
        historical_expanding_average
        activity_ratio_7d
        activity_ratio_30d

    The historical expanding average is shifted by one day so the value for
    a date uses only prior dates. This prevents future-data leakage when the
    table is later used for anomaly detection or forecasting.
    """

    required_columns = {"date", "event_count"}

    missing_columns = required_columns.difference(
        daily_activity.columns
    )

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            "Daily activity data is missing required columns: "
            f"{missing_text}"
        )

    metrics = daily_activity.copy()

    metrics["date"] = pd.to_datetime(
        metrics["date"],
        errors="coerce",
    )

    metrics["event_count"] = pd.to_numeric(
        metrics["event_count"],
        errors="coerce",
    ).fillna(0)

    metrics = (
        metrics.dropna(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    metrics["event_count_7d"] = (
        metrics["event_count"]
        .rolling(window=7, min_periods=1)
        .sum()
    )

    metrics["event_count_30d"] = (
        metrics["event_count"]
        .rolling(window=30, min_periods=1)
        .sum()
    )

    metrics["daily_average_7d"] = (
        metrics["event_count"]
        .rolling(window=7, min_periods=1)
        .mean()
    )

    metrics["daily_average_30d"] = (
        metrics["event_count"]
        .rolling(window=30, min_periods=1)
        .mean()
    )

    metrics["historical_expanding_average"] = (
        metrics["event_count"]
        .expanding(min_periods=1)
        .mean()
        .shift(1)
    )

    historical_average = metrics[
        "historical_expanding_average"
    ]

    metrics["activity_ratio_7d"] = (
        metrics["daily_average_7d"]
        .div(historical_average)
        .where(historical_average.gt(0))
    )

    metrics["activity_ratio_30d"] = (
        metrics["daily_average_30d"]
        .div(historical_average)
        .where(historical_average.gt(0))
    )

    integer_columns = [
        "event_count",
        "event_count_7d",
        "event_count_30d",
    ]

    metrics[integer_columns] = (
        metrics[integer_columns]
        .round()
        .astype("int64")
    )

    decimal_columns = [
        "daily_average_7d",
        "daily_average_30d",
        "historical_expanding_average",
        "activity_ratio_7d",
        "activity_ratio_30d",
    ]

    metrics[decimal_columns] = metrics[decimal_columns].round(4)

    return metrics


def summarize_activity(
    daily_activity: pd.DataFrame,
) -> ActivitySummary:
    """Create a period-level summary from daily activity metrics."""

    required_columns = {
        "date",
        "event_count",
        "magnitude_1_plus",
        "magnitude_2_plus",
        "magnitude_3_plus",
        "magnitude_4_plus",
        "magnitude_5_plus",
    }

    missing_columns = required_columns.difference(
        daily_activity.columns
    )

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            "Daily activity data is missing required columns: "
            f"{missing_text}"
        )

    if daily_activity.empty:
        return ActivitySummary(
            total_events=0,
            active_days=0,
            calendar_days=0,
            average_events_per_day=0.0,
            median_events_per_day=0.0,
            maximum_events_in_one_day=0,
            busiest_day=None,
            magnitude_1_plus=0,
            magnitude_2_plus=0,
            magnitude_3_plus=0,
            magnitude_4_plus=0,
            magnitude_5_plus=0,
        )

    activity = daily_activity.copy()

    activity["date"] = pd.to_datetime(
        activity["date"],
        errors="coerce",
    )

    count_columns = [
        "event_count",
        "magnitude_1_plus",
        "magnitude_2_plus",
        "magnitude_3_plus",
        "magnitude_4_plus",
        "magnitude_5_plus",
    ]

    for column in count_columns:
        activity[column] = pd.to_numeric(
            activity[column],
            errors="coerce",
        ).fillna(0)

    activity = activity.dropna(subset=["date"])

    if activity.empty:
        return summarize_activity(
            pd.DataFrame(
                columns=list(required_columns)
            )
        )

    busiest_index = activity["event_count"].idxmax()
    busiest_row = activity.loc[busiest_index]

    return ActivitySummary(
        total_events=int(activity["event_count"].sum()),
        active_days=int(activity["event_count"].gt(0).sum()),
        calendar_days=int(len(activity)),
        average_events_per_day=round(
            float(activity["event_count"].mean()),
            3,
        ),
        median_events_per_day=round(
            float(activity["event_count"].median()),
            3,
        ),
        maximum_events_in_one_day=int(
            busiest_row["event_count"]
        ),
        busiest_day=pd.Timestamp(
            busiest_row["date"]
        ).date().isoformat(),
        magnitude_1_plus=int(
            activity["magnitude_1_plus"].sum()
        ),
        magnitude_2_plus=int(
            activity["magnitude_2_plus"].sum()
        ),
        magnitude_3_plus=int(
            activity["magnitude_3_plus"].sum()
        ),
        magnitude_4_plus=int(
            activity["magnitude_4_plus"].sum()
        ),
        magnitude_5_plus=int(
            activity["magnitude_5_plus"].sum()
        ),
    )