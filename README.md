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
