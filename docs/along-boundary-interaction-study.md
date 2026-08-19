# Athena Along-Boundary Interaction Study v1

## Purpose

The Along-Boundary Interaction Study is a retrospective descriptive extension of Earthquake Interaction Study v1.1. The earlier radial study found strong magnitude-dependent post-event clustering near major earthquakes, with the persistent M6+ excess decaying toward historical baseline beyond roughly 500 km in ordinary epicentral distance.

This study asks a narrower geometric question:

> When two historical M6+ earthquakes share the same PB2002 plate pair, does shortest mapped distance along the connected PB2002 boundary network organize their pre/post association pattern differently from ordinary epicentral great-circle distance?

The study does **not** assume that an earthquake propagates energy, stress, or rupture along the mapped path.

## Source geometry and citation

Boundary geometry, adjacent plate identifiers, and source-defined boundary classes come from:

**Bird, P. (2003). _An updated digital model of plate boundaries_. Geochemistry, Geophysics, Geosystems, 4, 1027. https://doi.org/10.1029/2001GC000252**

Athena retains the existing pinned PB2002 distribution provenance documented in `docs/research-sources.md` and `config/research_sources.json`.

## Prepared geometry

1. Each earthquake that already has prepared PB2002 context is projected onto its associated PB2002 digitization step.
2. PB2002 digitization steps are connected only at exact source endpoints; Athena does not invent fuzzy junctions.
3. Event pairs are routed by shortest mapped graph distance with the default routing scope restricted to the **same orientation-independent PB2002 plate pair**.
4. Pairs with missing projections, different plate pairs, or disconnected same-pair graph geometry remain explicitly unavailable.
5. International-date-line geometry is handled on the sphere.

The resulting distance is called **along-boundary distance**. It is a mapped tectonic-geometry variable only.

## Study cohort and windows

The frozen research cohort remains the complete calendar-year window 1976-01-01 through 2026-01-01 with preferred USGS magnitude >= 6.0.

Directional descriptive summaries use source thresholds:

- M7.0+
- M7.5+
- M8.0+

Matched pre/post time windows:

- 1 day
- 7 days
- 30 days
- 90 days
- 365 days

Distance windows:

- 0-100 km
- 100-250 km
- 250-500 km
- 500-1,000 km
- 1,000-2,000 km

The raw cumulative windows are retained and non-overlapping annuli are derived in the summary.

## Apples-to-apples radial comparison

For each route-available event pair, Athena records both:

- shortest mapped same-plate-pair PB2002 graph distance; and
- ordinary epicentral great-circle distance.

The pre/post along-boundary and radial summaries therefore operate on the same route-available pair universe. This avoids comparing a restricted tectonic subset against an unrelated global radial denominator.

## Prepared artifacts

- `along_boundary_pairs.csv`: chronological pair-level route availability, radial distance, along-boundary distance, plate/boundary context, and explicit unavailable-route status.
- `along_boundary_windows.csv`: source-event matched pre/post counts for along-boundary and routed-radial distance definitions.
- `along_boundary_summary.json`: magnitude-stratified cumulative and annular summaries, route coverage, graph metadata, and scientific limitations.

## Inference status

V1 is **descriptive only**. It reports no p-values or statistical-significance claims because source-event windows overlap and are not independent.

The next inferential milestone is a dependence-aware randomized/null model that preserves source magnitude and tectonic context before Athena assesses whether an observed along-boundary pattern is unusual relative to historical controls.

## Required scientific limitations

- The cohort contains M6.0+ earthquakes only and does not represent ordinary lower-magnitude aftershock populations.
- Epicenters are projected to nearest prepared PB2002 boundary context; the mapped boundary is not necessarily the earthquake rupture fault.
- PB2002 is a generalized global plate-boundary model published in 2003 and does not resolve all local fault complexity.
- A shortest graph route is **not** a rupture path, Coulomb-stress path, dynamic-triggering path, energy-transfer path, or causal mechanism.
- Missing or disconnected routes are not fabricated.
- Overlapping windows create statistical dependence.
- V1 is retrospective and nonpredictive and produces no future-earthquake probability.
