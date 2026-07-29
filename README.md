# Project Athena

**Experimental seismic intelligence and probabilistic earthquake forecasting for Puerto Rico**

Project Athena is an open-source research platform that analyzes historical and near-real-time earthquake data for Puerto Rico and the surrounding Caribbean region.

Athena is designed to:

- Build a reliable historical earthquake catalog.
- Measure current seismic activity against historical patterns.
- Detect unusual clusters, swarms, and changes in seismic behavior.
- Develop transparent statistical and machine-learning models.
- Generate experimental, probability-based seismic outlooks.
- Provide explainable analytical results to Project Seismic.

> **Important:** Project Athena does not predict the exact time, location, or magnitude of future earthquakes. It is an experimental research and educational platform, not an official warning system.

---

## Project Mission

Project Athena exists to make Puerto Rico seismic data easier to understand, analyze, and responsibly model.

The project will combine:

- Data engineering
- Statistical analysis
- Geospatial analytics
- Time-series analysis
- Anomaly detection
- Machine learning
- Model explainability
- Reproducible research

The long-term goal is to create a transparent seismic intelligence engine that supports Project Seismic while clearly separating experimental analysis from official earthquake and tsunami alerts.

---

## Scientific Position

Athena will not claim that earthquakes can be predicted with certainty.

The platform will focus on scientifically defensible outputs such as:

- Historical earthquake rates
- Seismic activity baselines
- Earthquake clustering
- Swarm identification
- Aftershock behavior
- Magnitude and depth trends
- Statistical anomalies
- Probability estimates for defined future time windows

An example research target is:

> What is the estimated probability that a Puerto Rico seismic zone will experience at least one magnitude 3.0 or greater earthquake during the next seven days?

All forecasts must include:

- A defined geographic region
- A defined magnitude threshold
- A defined forecast period
- A probability estimate
- A historical baseline
- A confidence or reliability indicator
- An explanation of the primary factors
- A visible disclaimer

---

## Version 1 Objective

The first version of Athena will not use machine learning.

Version 1 will create the **Puerto Rico Seismic Observatory**, a clean and reproducible analytical foundation for understanding Puerto Rico’s earthquake history.

The initial release will answer:

- How many earthquakes occur each day, month, and year?
- Where are earthquakes most concentrated?
- How does seismic activity vary by region?
- What magnitude ranges are most common?
- How does earthquake depth vary over time and location?
- What does a normal day, week, or month of activity look like?
- When does current activity exceed historical expectations?
- How do major sequences and aftershock periods differ from normal activity?

---

## Initial Study Region

The initial geographic boundaries are:

| Boundary | Value |
|---|---:|
| Minimum latitude | 17.0 |
| Maximum latitude | 20.0 |
| Minimum longitude | -69.0 |
| Maximum longitude | -63.5 |

These boundaries include Puerto Rico and surrounding seismic regions such as:

- Southwest Puerto Rico
- Mona Passage
- Puerto Rico Trench
- Virgin Islands
- Anegada Passage
- Northern Puerto Rico
- Southern Puerto Rico

The exact zone definitions will be documented and version-controlled before they are used in modeling.

---

## Initial Data Sources

The first historical catalog will use earthquake event data from the United States Geological Survey.

Future versions may incorporate:

- Puerto Rico Seismic Network catalogs
- Seismic station information
- Fault and tectonic boundary data
- Waveform data
- GPS crustal-deformation data
- Tsunami-related observations

Each data source must be documented with:

- Source organization
- Access method
- Retrieval date
- Geographic coverage
- Time coverage
- Known limitations
- Processing steps
- Licensing or attribution requirements

---

## Repository Structure

```text
project-athena/
├── config/
│   └── Project configuration and geographic definitions
│
├── data/
│   ├── raw/
│   │   └── Original downloaded data that has not been modified
│   ├── processed/
│   │   └── Cleaned and analysis-ready datasets
│   └── reference/
│       └── Geographic zones, fault data, and supporting references
│
├── notebooks/
│   └── Exploratory analysis and documented research experiments
│
├── outputs/
│   └── Generated forecasts, reports, charts, and model results
│
├── src/
│   ├── ingestion/
│   │   └── Data-download and source-integration code
│   ├── features/
│   │   └── Feature engineering and target construction
│   ├── models/
│   │   └── Statistical and machine-learning models
│   └── pipelines/
│       └── End-to-end executable workflows
│
├── tests/
│   └── Automated tests for data and application logic
│
├── .gitignore
├── requirements.txt
└── README.md
```

## Historical catalog ingestion

`src.catalog` provides a reusable, deterministic ingestion pipeline for USGS
historical GeoJSON data. It is region-agnostic; Puerto Rico can be queried with
the documented study bounds, while callers may supply any valid rectangular
bounds. Records are normalized to `event_id`, `time`, `latitude`, `longitude`,
`depth`, `magnitude`, `magnitude_type`, `place`, `event_type`, `source`, and
`updated_time`. Timestamps are UTC, malformed or incomplete records are counted
and excluded, and duplicate source/event IDs retain the most recently updated
record before sorting by event time and ID.

```python
from datetime import datetime, timezone
from src.catalog import (
    CatalogQuery, GeographicBounds, export_csv, ingest_historical_catalog,
)

query = CatalogQuery(
    start_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
    end_time=datetime(2020, 2, 1, tzinfo=timezone.utc),
    bounds=GeographicBounds(17.0, 20.0, -69.0, -63.5),  # Puerto Rico region
    minimum_magnitude=1.0,
)
result = ingest_historical_catalog(query)
export_csv(result, "outputs/puerto_rico_2020_01.csv")
print(result.summary.to_dict())
```

For tests or offline ingestion, pass a client object with a `fetch(query)` method
that returns USGS GeoJSON features. The pipeline itself makes no assumptions
about a particular location and does not make predictive claims.

## Historical activity baselines

`src.baseline` provides deterministic descriptive baselines across UTC calendar
days, Monday-start weeks, or calendar months. It includes zero-event periods so
quiet intervals remain part of the historical distribution.

```python
from datetime import datetime, timezone
import pandas as pd

from src.baseline import BaselineConfiguration, calculate_historical_baselines, compare_current_period

historical_catalog = pd.DataFrame({
    "time": ["2024-01-01T12:00:00Z", "2024-01-03T08:00:00Z"],
    "magnitude": [2.1, 3.0],
    "depth": [8.0, 12.0],
})
baseline = calculate_historical_baselines(
    historical_catalog, BaselineConfiguration(period="daily")
)
comparison = compare_current_period(
    pd.DataFrame({"time": [], "magnitude": [], "depth": []}), baseline,
    current_start=datetime(2024, 2, 1, tzinfo=timezone.utc),
    current_end=datetime(2024, 2, 8, tzinfo=timezone.utc),
)
print(comparison.metrics["event_count"].classification)
```

Baseline and comparison outputs are descriptive historical analytics, not
earthquake predictions, future probabilities, official alerts, or warnings.

## Explainable anomaly scoring

`src.anomaly` converts an existing historical baseline and current-period
comparison into a deterministic, metric-by-metric anomaly score. It does not
recalculate the baseline: each configured metric uses the historical percentile
rank already produced by `src.baseline`. Higher-than-usual one-sided metrics
(event count, maximum magnitude, and total energy by default) contribute above
the 50th percentile, while mean depth is scored in both directions so unusually
shallow and unusually deep periods can be described.

```python
from src.anomaly import calculate_anomaly_score
from src.baseline import calculate_historical_baselines, compare_current_period

baseline = calculate_historical_baselines(historical_catalog)
comparison = compare_current_period(
    current_catalog,
    baseline,
    current_start="2024-02-01T00:00:00Z",
    current_end="2024-02-02T00:00:00Z",
)
anomaly = calculate_anomaly_score(comparison)
print(anomaly.summary)
```

This is a historical baseline → current-period comparison → anomaly score
workflow. The result retains each metric's value, historical mean, percentile,
direction, normalized weight, score contribution, and explanation so the
composite is auditable.

> **Important:** Anomaly scores are descriptive comparisons with historical
> seismic activity. They do not predict earthquakes, estimate future earthquake
> probability, or replace official earthquake and tsunami alerts.

## Temporal anomaly trends

`src.trends` describes how previously calculated anomaly scores move across
ordered observation periods. It consumes anomaly results directly; it does not
recalculate baselines or anomaly scores, infer the spacing between periods, or
make a forecast.

```python
from src.trends import calculate_temporal_trend

trend = calculate_temporal_trend(tuple(anomaly_results))
print(trend.summary)
```

Each trend point contains trailing short-, medium-, and long-window arithmetic
moving averages calculated from available scores only. The result also reports
an ordinary-least-squares slope in score points per observation period, the
latest score's momentum relative to its short moving average, and the change
between non-overlapping previous and current slopes (acceleration). Consecutive
strict increases and decreases describe persistence. Direction and strength are
deterministic descriptive classifications based on configured score-movement,
persistence, and historical first-to-latest change thresholds. Unavailable
scores remain represented in the output but never count as zero or enter these
numeric calculations.

> **Important:** Temporal trend results describe changes in historical anomaly
> scores. They do not predict earthquakes, estimate future earthquake
> probability, or replace official earthquake and tsunami alerts.

## Observatory time-series builder

`src.timeseries` builds a deterministic sequence of calendar-aligned historical
comparisons, anomaly results, and one final temporal trend directly from a
seismic catalog. Daily periods start at midnight UTC, weekly periods start on
Monday at midnight UTC, and monthly periods use true calendar-month boundaries.
All generated periods are non-overlapping half-open intervals (`[start, end)`).
Naive catalog timestamps are interpreted as UTC; an explicit `analysis_start`
is aligned down to its containing period, while an explicit `analysis_end` is a
hard bound and omits a final partial natural period.

```python
from src.timeseries import (
    TimeSeriesConfiguration,
    TimeSeriesFrequency,
    build_observatory_time_series,
)

configuration = TimeSeriesConfiguration(
    frequency=TimeSeriesFrequency.DAILY,
    baseline_lookback_periods=30,
    minimum_baseline_periods=7,
)

result = build_observatory_time_series(catalog, configuration)
print(result.summary)
print(result.trend.summary)
```

For every eligible observation period, the builder uses a rolling window of
complete preceding calendar periods and invokes the public baseline,
current-period comparison, anomaly-scoring, and temporal-trend APIs. The
baseline ends exactly at the current period start, so it cannot contain current
or future events. Empty current periods are valid zero-event observations.
Periods without enough covered history or without a usable baseline are retained
with a deterministic unavailable reason by default; setting
`include_unavailable_periods=False` hides only those points and does not change
counts, anomaly results, or trend input. An anomaly object with `score=None` is
still an available builder point and remains in the final trend sequence.
Results are immutable and provide deterministic JSON-serializable `to_dict()`
output.

> **Important:** Observatory time-series results describe historical seismic
> activity and anomaly-score behavior. They do not predict earthquakes,
> estimate future earthquake probability, or replace official earthquake and
> tsunami alerts.

## Unified Observatory intelligence report

The legacy Observatory report remains available with `python -m src.observatory.report`.
It summarizes catalog activity, magnitude, estimated energy, depth, and a threshold-based
Observatory status. The unified report adds the existing historical baseline comparisons,
explainable anomaly scores, complete time series, a descriptive temporal trend, and the
most recent periods. It does not recalculate those analytical layers.

```bash
python -m src.observatory.report --intelligence
python -m src.observatory.report --intelligence --frequency daily \
  --baseline-lookback 30 --minimum-baseline-periods 7 --recent-periods 10
```

```python
from src.observatory import (
    ObservatoryIntelligenceConfiguration,
    build_observatory_intelligence_report,
)
report = build_observatory_intelligence_report(
    configuration=ObservatoryIntelligenceConfiguration(),
)
print(report.executive_summary)
```

Observatory status is a threshold-based descriptive classification. Anomaly level describes
how unusual observed metrics are against historical baselines, while the temporal trend
describes movement in historical anomaly scores. Recent periods are the latest configured
number of chronological periods. None of these outputs predicts a future earthquake.

> Project Athena reports describe historical seismic observations and analytical anomaly behavior. They are descriptive and nonpredictive. They do not predict earthquakes, estimate future earthquake probability, determine imminent danger, or replace official earthquake, tsunami, or emergency-management information.
