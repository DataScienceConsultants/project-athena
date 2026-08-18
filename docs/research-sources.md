# Project Athena research sources and citation policy

Project Athena treats source provenance as part of every prepared research artifact. A dataset used by a research workflow should be traceable to the scientific work or authoritative service that defines it, the exact distributed bytes used by Athena when practical, and the license or redistribution terms attached to that distribution.

Generated research bundle metadata embeds compact citation/provenance records from `config/research_sources.json`. This document provides the human-readable companion bibliography and explains how Athena distinguishes scientific attribution from distribution provenance.

## Citation and reproducibility rules

1. Cite the scientific or authoritative source that defines the data or method.
2. Pin mutable machine-readable sources by an immutable revision and checksum whenever practical.
3. Record distribution licensing separately from scientific authorship.
4. Preserve source-defined categories and fields. Athena may normalize representation for computation, but it must not silently invent tectonic classifications.
5. Keep geographic context distinct from causality. Fault or plate-boundary proximity does not imply that a mapped structure caused an earthquake or that a future event is more likely.
6. Distinguish **implemented methodology** from **physical/scientific context**. A cited paper must not be described as an Athena calculation unless Athena actually implements and tests that calculation.

## Operational earthquake catalog

### USGS ComCat

**U.S. Geological Survey. _USGS Earthquake Catalog (ComCat) FDSN Event Web Service_.**

Athena uses the USGS FDSN event service as the operational source for the frozen global research catalog. The global planner preflights and partitions requests to remain below service result limits. Catalog coverage and source limitations remain explicit in bundle metadata.

### USGS magnitude types

**U.S. Geological Survey. _Magnitude Types_.**

Athena uses the USGS magnitude-type definitions to decide whether a preferred catalog magnitude belongs to the Mw family. Only `Mw`, `Mww`, `Mwc`, `Mwb`, `Mwr`, and `Mwp` are eligible for Athena's scalar seismic-moment conversion in the Earthquake Interaction Study. Other magnitude types remain unconverted rather than being silently treated as moment magnitude.

## Active-fault context

### GEM Global Active Faults Database

**Global Earthquake Model Foundation. _GEM Global Active Faults Database_.**

Athena uses the project's GeoJSON version of record for mapped active-fault geographic context. The configured source revision is checksum-verified before it is admitted to a generated research bundle. Nearest-fault associations are descriptive geographic context only and are not causal attribution.

## Plate-boundary context

### Bird PB2002

**Bird, P. (2003). _An updated digital model of plate boundaries_. Geochemistry, Geophysics, Geosystems, 4, 1027. https://doi.org/10.1029/2001GC000252**

Athena uses the PB2002 digitization-step data because the source explicitly records the two adjacent plate identifiers, boundary geometry, relative plate velocity components, and seven source-defined boundary classes. Athena preserves those source fields rather than deriving its own tectonic class labels.

For reproducibility, Athena currently retrieves the original PB2002 supporting-data file from a pinned mirror:

- Distribution repository: `fraxen/tectonicplates`
- Pinned commit: `339b0c56563c118307b1f4542703047f5f698fae`
- File: `original/PB2002_steps.dat.txt`
- Git blob SHA: `b48506d79c614b241ce26cf949492ee7c6676d60`
- Mirror collection license: Open Data Commons Attribution License 1.0 (`ODC-By-1.0`)

The mirror is used as immutable distribution provenance. **Scientific attribution remains Bird (2003).** The mirror's ODC-By license is recorded as the distribution license and is not presented as the license of the scholarly article itself.

PB2002 plate-boundary proximity and plate-pair membership are retrospective tectonic context. They are not proof that one earthquake caused another and are not a future-earthquake probability estimate.

## Independent large-event reference

### ISC-GEM Global Instrumental Earthquake Catalogue

**International Seismological Centre. _ISC-GEM Global Instrumental Earthquake Catalogue_, version 12.1. https://doi.org/10.31905/D808B825**

Athena records ISC-GEM as an independent homogeneous large-event reference and completeness cross-check. It is not used as an unqualified replacement for the operational ComCat cohort.

## Earthquake Interaction Study v1.1

Earthquake Interaction Study v1.1 is a **retrospective descriptive association study** over the frozen global M6.0+ cohort. For every qualifying source event, Athena measures M6.0+ activity before and after the source event using paired 1-, 7-, 30-, 90-, and 365-day windows and cumulative 100-, 250-, 500-, 1,000-, and 2,000-km epicentral distance windows.

For each source/window combination, Athena records:

- all qualifying nearby events before and after the source event;
- events sharing the same orientation-independent PB2002 plate pair;
- events sharing the same PB2002 boundary identifier;
- whether the pre and post windows are complete within the frozen catalog bounds;
- source magnitude type and scalar seismic moment when the preferred magnitude is an Mw-family magnitude.

V1.1 deliberately reports descriptive pre/post counts and ratios without p-values. Observation windows overlap, so treating each source event as statistically independent would be unjustified. A later inferential version must introduce and validate a dependence-aware null model before Athena reports statistical significance.

### V1.1 correction: pair symmetry and source-size strata

The first v1 durable bundle demonstrated an important accounting property: if the same M6.0+ catalog is used as both the source population and the target population, an earthquake pair can appear once as a post-event for the earlier source and once as a pre-event for the later source. Summing across the entire identical source/target cohort therefore drives the global aggregate toward pre/post symmetry, apart from catalog-edge eligibility differences.

V1.1 keeps the all-source aggregate for transparency, but marks it as unsuitable for directional interpretation. Directional descriptive analysis is instead reported for larger source-event strata:

- M7.0+ sources;
- M7.5+ sources;
- M8.0+ sources.

The target population remains the frozen M6.0+ cohort. This breaks the simple pair-count symmetry and lets Athena ask whether progressively larger source earthquakes are followed by different M6.0+ activity patterns than occurred before those larger sources. These strata are still descriptive and overlapping; they do not establish causation or statistical significance.

### V1.1 correction: non-overlapping distance annuli

The original distance windows are cumulative. For example, the 2,000-km count also includes every event within 100, 250, 500, and 1,000 km. A large apparent 2,000-km signal can therefore be produced entirely by near-source events.

V1.1 additionally reports non-overlapping distance annuli by subtracting adjacent cumulative windows:

- 0–100 km;
- 100–250 km;
- 250–500 km;
- 500–1,000 km;
- 1,000–2,000 km.

These annuli are intended to distinguish near-source clustering from broader spatial association. They remain epicentral great-circle distance bands, not rupture-to-rupture or along-plate-boundary distances.

### Implemented scalar seismic-moment relation

**Hanks, T. C., & Kanamori, H. (1979). _A moment magnitude scale_. Journal of Geophysical Research, 84(B5), 2348-2350. https://doi.org/10.1029/JB084iB05p02348**

For USGS Mw-family preferred magnitudes only, Athena implements the SI relation

`Mw = 2/3 (log10 M0 - 9.1)`

or equivalently

`M0 = 10^(1.5 Mw + 9.1) N m`.

Athena labels this quantity **scalar seismic moment**, not transferred energy. Non-Mw magnitudes are not silently converted.

### Physical context: earthquake-rate changes and clustering

**Dieterich, J. (1994). _A constitutive law for rate of earthquake production and its application to earthquake clustering_. Journal of Geophysical Research, 99(B2), 2601-2618. https://doi.org/10.1029/93JB02581**

Dieterich provides physical context for why earthquake rates may change after stress perturbations and for temporal clustering. Earthquake Interaction Study v1.1 does **not** implement a Dieterich rate-and-state inversion or infer stressing history.

### Physical context: static Coulomb stress triggering

**King, G. C. P., Stein, R. S., & Lin, J. (1994). _Static stress changes and the triggering of earthquakes_. Bulletin of the Seismological Society of America, 84(3), 935-953. https://doi.org/10.1785/BSSA0840030935**

King, Stein, and Lin provide the physical basis for later Coulomb-stress research. V1.1 does **not** calculate Coulomb stress because the frozen catalog/plate-context layer does not yet provide the rupture geometry, slip model, receiver-fault orientation, and frictional assumptions required for such a calculation.

### Physical context and caution: dynamic triggering

**Brodsky, E. E., & Prejean, S. G. (2005). _New constraints on mechanisms of remotely triggered seismicity at Long Valley Caldera_. Journal of Geophysical Research, 110, B04302. https://doi.org/10.1029/2004JB003211**

Brodsky and Prejean document remotely triggered seismicity and show why cumulative shaking energy density alone is not a sufficient explanation for the observed triggering at Long Valley. Athena therefore does not interpret a large source magnitude, scalar seismic moment, or subsequent catalog association as proof that earthquake energy caused a later event.

## V1.1 limitations that must remain visible

- The cohort contains M6.0+ events only and cannot describe ordinary lower-magnitude aftershock populations.
- Spatial separation is epicentral great-circle distance, not rupture-to-rupture distance or along-boundary path length.
- PB2002 relationships are nearest mapped tectonic context and are not causal attribution.
- V1.1 does not calculate static Coulomb stress, dynamic wave stress, rupture propagation, slip transfer, or receiver-fault loading.
- Overlapping windows create dependence; v1.1 therefore does not report p-values or claim statistical significance.
- The all-M6+ aggregate is pair-symmetric by construction and is retained only as a transparent baseline; directional interpretation uses the larger-source strata.
- Scalar seismic moment is a source-size variable and is not labeled transferred energy.
- The study is retrospective, descriptive, and nonpredictive.
