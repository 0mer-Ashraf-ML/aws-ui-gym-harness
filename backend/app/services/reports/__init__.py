"""Report generation utilities for execution results."""

from .execution_report import (
    generate_execution_report, 
    generate_combined_report,
    IterationRecord,
    collect_execution_data
)

__all__ = [
    "generate_execution_report", 
    "generate_combined_report",
    "IterationRecord",
    "collect_execution_data"
]
