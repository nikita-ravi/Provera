"""
MediGraph Evaluation & Observability Module

Components:
- golden_set: Manually verified communities for classification testing
- factual_accuracy: Verifies LLM outputs against source data
- observability: Structured logging and metrics collection
- run_evals: CLI for running evaluations
"""

from .golden_set import GOLDEN_SET, get_golden_set, get_by_class
from .factual_accuracy import FactualAccuracyChecker, FactualAccuracyResult
from .observability import (
    InvestigationTracer,
    InvestigationTrace,
    MetricsSummary,
    analyze_traces,
    print_metrics_dashboard
)

__all__ = [
    "GOLDEN_SET",
    "get_golden_set",
    "get_by_class",
    "FactualAccuracyChecker",
    "FactualAccuracyResult",
    "InvestigationTracer",
    "InvestigationTrace",
    "MetricsSummary",
    "analyze_traces",
    "print_metrics_dashboard",
]
