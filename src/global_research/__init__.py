"""Public API for Athena's retrospective global seismic/fault research layer."""

from src.global_research.catalog import (
    CatalogCountError,
    GlobalCatalogDownload,
    USGSCatalogCounter,
    download_global_catalog,
    export_global_catalog_csv,
)
from src.global_research.fault_index import (
    FaultGridIndex,
    associate_catalog_events_indexed,
)
from src.global_research.faults import (
    DEFAULT_FAULT_SOURCE,
    associate_catalog_events,
    distance_to_fault_km,
    great_circle_segment_distance_km,
    load_fault_geojson,
    nearest_fault,
)
from src.global_research.models import (
    GLOBAL_BOUNDS,
    REFERENCE_50_YEAR_PROFILE,
    FaultAssociation,
    FaultTrace,
    GlobalCatalogPlan,
    GlobalResearchProfile,
    PlannedCatalogQuery,
)
from src.global_research.planner import (
    AdaptiveGlobalCatalogPlanner,
    CatalogPlanningError,
    planned_query_as_catalog_query,
    reference_50_year_plan,
)
from src.global_research.runner import (
    GlobalResearchBundle,
    run_global_research,
    run_reference_50_year_research,
)
from src.global_research.sources import (
    ResearchSourceError,
    download_gem_global_active_faults,
    download_verified_geojson,
    git_blob_sha,
    load_research_sources,
)

__all__ = [
    "AdaptiveGlobalCatalogPlanner",
    "CatalogCountError",
    "CatalogPlanningError",
    "DEFAULT_FAULT_SOURCE",
    "FaultAssociation",
    "FaultGridIndex",
    "FaultTrace",
    "GLOBAL_BOUNDS",
    "GlobalCatalogDownload",
    "GlobalCatalogPlan",
    "GlobalResearchBundle",
    "GlobalResearchProfile",
    "PlannedCatalogQuery",
    "REFERENCE_50_YEAR_PROFILE",
    "ResearchSourceError",
    "USGSCatalogCounter",
    "associate_catalog_events",
    "associate_catalog_events_indexed",
    "distance_to_fault_km",
    "download_gem_global_active_faults",
    "download_global_catalog",
    "download_verified_geojson",
    "export_global_catalog_csv",
    "git_blob_sha",
    "great_circle_segment_distance_km",
    "load_fault_geojson",
    "load_research_sources",
    "nearest_fault",
    "planned_query_as_catalog_query",
    "reference_50_year_plan",
    "run_global_research",
    "run_reference_50_year_research",
]
