# Project Athena research sources and citation policy

Project Athena treats source provenance as part of every prepared research artifact. A dataset used by a research workflow should be traceable to the scientific work or authoritative service that defines it, the exact distributed bytes used by Athena when practical, and the license or redistribution terms attached to that distribution.

Generated research bundle metadata embeds compact citation/provenance records from `config/research_sources.json`. This document provides the human-readable companion bibliography and explains how Athena distinguishes scientific attribution from distribution provenance.

## Citation and reproducibility rules

1. Cite the scientific or authoritative source that defines the data or method.
2. Pin mutable machine-readable sources by an immutable revision and checksum whenever practical.
3. Record distribution licensing separately from scientific authorship.
4. Preserve source-defined categories and fields. Athena may normalize representation for computation, but it must not silently invent tectonic classifications.
5. Keep geographic context distinct from causality. Fault or plate-boundary proximity does not imply that a mapped structure caused an earthquake or that a future event is more likely.
6. Add methodology papers only when the corresponding methodology is actually implemented in Athena.

## Operational earthquake catalog

### USGS ComCat

**U.S. Geological Survey. _USGS Earthquake Catalog (ComCat) FDSN Event Web Service_.**

Athena uses the USGS FDSN event service as the operational source for the frozen global research catalog. The global planner preflights and partitions requests to remain below service result limits. Catalog coverage and source limitations remain explicit in bundle metadata.

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

## Future interaction and stress-response methodology

The planned Earthquake Interaction Study will require its own methodology citations for any implemented physical or statistical model. Relevant literature may include seismic moment/energy relations, static Coulomb stress transfer, rate-and-state seismicity response, and dynamic triggering. These works should be added to Athena's formal methodology bibliography only when their equations or methods are actually implemented and tested; they should not be cited as if they already define the current plate-context layer.
