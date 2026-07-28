"""Public interface for Project Athena observatory reporting."""

from src.observatory.builder import (
    build_observatory_report,
    build_observatory_report_from_dataframe,
)

build_observatory_intelligence_report = build_observatory_report

__all__ = [
    "build_observatory_intelligence_report",
    "build_observatory_report",
    "build_observatory_report_from_dataframe",
]