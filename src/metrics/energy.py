"""Estimated seismic-energy metrics for Project Athena.

The energy values calculated here are approximate and are intended for
comparative analysis. They do not represent direct measurements of the
total physical energy released by an earthquake.

The estimation used is:

    energy_joules = 10 ** (1.5 * magnitude + 4.8)
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True, slots=True)
class EnergySummary:
    """Summary of estimated seismic energy over a selected period."""

    event_count_with_magnitude: int
    total_energy_joules: float
    average_energy_joules: float
    median_energy_joules: float
    maximum_event_energy_joules: float
    maximum_energy_magnitude: float | None
    maximum_energy_event_id: str | None
    equivalent_single_magnitude: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return the summary as a dictionary."""

        return asdict(self)


def magnitude_to_energy_joules(
    magnitude: float | int | None,
) -> float | None:
    """Estimate seismic energy in joules from earthquake magnitude.

    Args:
        magnitude: Numeric earthquake magnitude.

    Returns:
        Estimated energy in joules, or None when magnitude is unavailable.

    Raises:
        TypeError: When magnitude is not numeric.
        ValueError: When magnitude is not finite.
    """

    if magnitude is None:
        return None

    if isinstance(magnitude, bool):
        raise TypeError("Magnitude must be numeric, not boolean.")

    try:
        numeric_magnitude = float(magnitude)
    except (TypeError, ValueError) as exc:
        raise TypeError("Magnitude must be numeric.") from exc

    if not math.isfinite(numeric_magnitude):
        raise ValueError("Magnitude must be finite.")

    return 10 ** (1.5 * numeric_magnitude + 4.8)


def energy_joules_to_equivalent_magnitude(
    energy_joules: float | int | None,
) -> float | None:
    """Convert estimated energy into an equivalent single magnitude.

    This answers the comparative question:

        What magnitude earthquake would release approximately the same
        estimated energy as this collection of earthquakes?
    """

    if energy_joules is None:
        return None

    if isinstance(energy_joules, bool):
        raise TypeError("Energy must be numeric, not boolean.")

    try:
        numeric_energy = float(energy_joules)
    except (TypeError, ValueError) as exc:
        raise TypeError("Energy must be numeric.") from exc

    if not math.isfinite(numeric_energy):
        raise ValueError("Energy must be finite.")

    if numeric_energy <= 0:
        return None

    return (math.log10(numeric_energy) - 4.8) / 1.5


def add_event_energy(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Add estimated energy to an event-level earthquake catalog.

    Required columns:

        event_id
        magnitude

    Added column:

        estimated_energy_joules
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Catalog must be a pandas DataFrame.")

    required_columns = {"event_id", "magnitude"}
    missing_columns = required_columns.difference(dataframe.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"Catalog is missing required columns: {missing_text}"
        )

    catalog = dataframe.copy()

    catalog["magnitude"] = pd.to_numeric(
        catalog["magnitude"],
        errors="coerce",
    )

    catalog["estimated_energy_joules"] = catalog[
        "magnitude"
    ].map(
        lambda value: (
            magnitude_to_energy_joules(value)
            if pd.notna(value)
            else float("nan")
        )
    )

    return catalog


def build_daily_energy(
    dataframe: pd.DataFrame,
    *,
    include_inactive_days: bool = True,
) -> pd.DataFrame:
    """Aggregate event-level energy into one row per UTC calendar day.

    Required columns:

        event_id
        event_time_utc
        magnitude

    Output columns:

        date
        event_count
        events_with_magnitude
        total_energy_joules
        average_energy_joules
        maximum_event_energy_joules
        equivalent_single_magnitude
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Catalog must be a pandas DataFrame.")

    required_columns = {
        "event_id",
        "event_time_utc",
        "magnitude",
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

    catalog = catalog.dropna(
        subset=["event_id", "event_time_utc"]
    )

    if catalog.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "event_count",
                "events_with_magnitude",
                "total_energy_joules",
                "average_energy_joules",
                "maximum_event_energy_joules",
                "equivalent_single_magnitude",
            ]
        )

    catalog = add_event_energy(catalog)

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
            total_energy_joules=(
                "estimated_energy_joules",
                "sum",
            ),
            average_energy_joules=(
                "estimated_energy_joules",
                "mean",
            ),
            maximum_event_energy_joules=(
                "estimated_energy_joules",
                "max",
            ),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    daily["equivalent_single_magnitude"] = daily[
        "total_energy_joules"
    ].map(energy_joules_to_equivalent_magnitude)

    count_columns = [
        "event_count",
        "events_with_magnitude",
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

        daily["total_energy_joules"] = daily[
            "total_energy_joules"
        ].fillna(0.0)

    return daily


def add_rolling_energy_metrics(
    daily_energy: pd.DataFrame,
) -> pd.DataFrame:
    """Add rolling energy totals and historical comparisons.

    Added columns:

        total_energy_7d_joules
        total_energy_30d_joules
        daily_average_energy_7d_joules
        daily_average_energy_30d_joules
        historical_expanding_energy_average_joules
        energy_ratio_7d
        energy_ratio_30d

    The historical expanding average is shifted one day to avoid using
    future information in later anomaly-detection or forecast features.
    """

    required_columns = {
        "date",
        "total_energy_joules",
    }

    missing_columns = required_columns.difference(
        daily_energy.columns
    )

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            "Daily energy data is missing required columns: "
            f"{missing_text}"
        )

    metrics = daily_energy.copy()

    metrics["date"] = pd.to_datetime(
        metrics["date"],
        errors="coerce",
    )

    metrics["total_energy_joules"] = pd.to_numeric(
        metrics["total_energy_joules"],
        errors="coerce",
    ).fillna(0.0)

    metrics = (
        metrics.dropna(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    energy = metrics["total_energy_joules"]

    metrics["total_energy_7d_joules"] = (
        energy.rolling(window=7, min_periods=1).sum()
    )

    metrics["total_energy_30d_joules"] = (
        energy.rolling(window=30, min_periods=1).sum()
    )

    metrics["daily_average_energy_7d_joules"] = (
        energy.rolling(window=7, min_periods=1).mean()
    )

    metrics["daily_average_energy_30d_joules"] = (
        energy.rolling(window=30, min_periods=1).mean()
    )

    metrics[
        "historical_expanding_energy_average_joules"
    ] = (
        energy.expanding(min_periods=1)
        .mean()
        .shift(1)
    )

    historical_average = metrics[
        "historical_expanding_energy_average_joules"
    ]

    metrics["energy_ratio_7d"] = (
        metrics["daily_average_energy_7d_joules"]
        .div(historical_average)
        .where(historical_average.gt(0))
    )

    metrics["energy_ratio_30d"] = (
        metrics["daily_average_energy_30d_joules"]
        .div(historical_average)
        .where(historical_average.gt(0))
    )

    return metrics


def summarize_energy(
    dataframe: pd.DataFrame,
) -> EnergySummary:
    """Create a period-level energy summary from event-level data."""

    energy_catalog = add_event_energy(dataframe)

    usable = energy_catalog.dropna(
        subset=["magnitude", "estimated_energy_joules"]
    )

    if usable.empty:
        return EnergySummary(
            event_count_with_magnitude=0,
            total_energy_joules=0.0,
            average_energy_joules=0.0,
            median_energy_joules=0.0,
            maximum_event_energy_joules=0.0,
            maximum_energy_magnitude=None,
            maximum_energy_event_id=None,
            equivalent_single_magnitude=None,
        )

    total_energy = float(
        usable["estimated_energy_joules"].sum()
    )

    maximum_index = usable[
        "estimated_energy_joules"
    ].idxmax()

    maximum_event = usable.loc[maximum_index]

    return EnergySummary(
        event_count_with_magnitude=int(len(usable)),
        total_energy_joules=total_energy,
        average_energy_joules=float(
            usable["estimated_energy_joules"].mean()
        ),
        median_energy_joules=float(
            usable["estimated_energy_joules"].median()
        ),
        maximum_event_energy_joules=float(
            maximum_event["estimated_energy_joules"]
        ),
        maximum_energy_magnitude=float(
            maximum_event["magnitude"]
        ),
        maximum_energy_event_id=str(
            maximum_event["event_id"]
        ),
        equivalent_single_magnitude=round(
            energy_joules_to_equivalent_magnitude(
                total_energy
            )
            or 0.0,
            4,
        ),
    )


def sum_event_energy(
    magnitudes: Iterable[float | int | None],
) -> float:
    """Return total estimated energy for an iterable of magnitudes."""

    total = 0.0

    for magnitude in magnitudes:
        energy = magnitude_to_energy_joules(magnitude)

        if energy is not None:
            total += energy

    return total