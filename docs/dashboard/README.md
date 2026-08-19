# Athena Research Dashboard

The Research Dashboard is the visual exploration surface for the immutable Project Athena global M6+ research bundle v5 (`research-global-m6-1976-2025-v5`).

It exposes:

- all 7,085 records in the frozen 1976–2025 M6+ catalog;
- filters and a global map for earthquakes, magnitude, year, boundary class, and record type;
- searchable M7+, M7.5+, M8+, and M9+ major-earthquake drilldowns;
- event-level Bird PB2002 plate-boundary context and nearest GEM active-fault context;
- routed M6+ relationships around major source earthquakes;
- per-source pre/post comparisons for 1, 7, 30, 90, and 365 days;
- the v5 radial-versus-along-boundary cumulative and annular study results;
- direct downloads of every raw artifact in the v5 bundle;
- the bundle's scientific citations and limitations.

## Data flow

The repository does not duplicate the complete research bundle in Git history. The Pages workflow downloads the immutable v5 GitHub Release, runs `scripts/build_research_dashboard_data.py`, copies the original raw artifacts into the deployed site, and builds compact browser indexes for interactive exploration.

The data adapter is presentation-only. It does not recompute or alter Athena's research statistics.

## Scientific status

The dashboard is retrospective, descriptive, and nonpredictive. A shortest PB2002 graph route is tectonic geometry context only; it is not a rupture path, stress-transfer path, dynamic-triggering path, energy-transfer path, causal mechanism, or future-earthquake probability.

The plate-boundary geometry and adjacent plate identifiers remain attributed to Bird (2003), *An updated digital model of plate boundaries*, DOI `10.1029/2001GC000252`, with the pinned PB2002 distribution provenance retained in the v5 metadata.
