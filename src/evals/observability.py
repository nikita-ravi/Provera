"""
Observability Module for MediGraph Agent

Provides structured logging, metrics collection, and monitoring capabilities.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from functools import wraps


# Default log directory
LOG_DIR = Path(__file__).parent.parent.parent.parent / "logs"


@dataclass
class ToolCall:
    """Record of a tool invocation."""
    name: str
    latency_ms: float
    success: bool
    error: Optional[str] = None
    args: Optional[Dict] = None


@dataclass
class LLMCall:
    """Record of an LLM invocation."""
    step: str  # "hypotheses", "evaluation", "dossier"
    latency_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    model: str = "claude-sonnet-4-20250514"


@dataclass
class InvestigationTrace:
    """Complete trace of an investigation."""
    trace_id: str
    timestamp: str
    mode: str  # "community", "npi", "region"
    target: str  # community_id, npi, or region name

    # Classification results
    classification: Optional[str] = None
    flags_triggered: int = 0
    downgraded: bool = False
    downgrade_reason: Optional[str] = None
    false_positive_warnings: List[str] = field(default_factory=list)

    # Performance metrics
    total_latency_ms: float = 0
    tool_calls: List[ToolCall] = field(default_factory=list)
    llm_calls: List[LLMCall] = field(default_factory=list)

    # Errors
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)


class InvestigationTracer:
    """Context manager for tracing investigations."""

    def __init__(self, mode: str, target: str, log_dir: Path = None):
        self.trace = InvestigationTrace(
            trace_id=f"{mode}_{target}_{int(time.time()*1000)}",
            timestamp=datetime.now().isoformat(),
            mode=mode,
            target=str(target)
        )
        self.log_dir = log_dir or LOG_DIR
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.trace.total_latency_ms = (time.time() - self.start_time) * 1000

        if exc_type is not None:
            self.trace.success = False
            self.trace.error = str(exc_val)

        # Save trace to log file
        self._save_trace()

        return False  # Don't suppress exceptions

    def record_tool_call(self, name: str, latency_ms: float, success: bool = True,
                         error: str = None, args: dict = None):
        """Record a tool invocation."""
        self.trace.tool_calls.append(ToolCall(
            name=name,
            latency_ms=latency_ms,
            success=success,
            error=error,
            args=args
        ))

    def record_llm_call(self, step: str, latency_ms: float,
                        input_tokens: int = None, output_tokens: int = None):
        """Record an LLM invocation."""
        self.trace.llm_calls.append(LLMCall(
            step=step,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        ))

    def record_classification(self, classification: str, flags_triggered: int,
                              downgraded: bool = False, downgrade_reason: str = None,
                              false_positive_warnings: List[str] = None):
        """Record classification results."""
        self.trace.classification = classification
        self.trace.flags_triggered = flags_triggered
        self.trace.downgraded = downgraded
        self.trace.downgrade_reason = downgrade_reason
        self.trace.false_positive_warnings = false_positive_warnings or []

    def _save_trace(self):
        """Save trace to log file."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y%m%d")
        log_file = self.log_dir / f"traces_{date_str}.jsonl"

        with open(log_file, "a") as f:
            f.write(self.trace.to_json().replace("\n", " ") + "\n")


def trace_tool(name: str):
    """Decorator to trace tool calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, _tracer: InvestigationTracer = None, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                latency = (time.time() - start) * 1000
                if _tracer:
                    _tracer.record_tool_call(name, latency, success=True)
                return result
            except Exception as e:
                latency = (time.time() - start) * 1000
                if _tracer:
                    _tracer.record_tool_call(name, latency, success=False, error=str(e))
                raise
        return wrapper
    return decorator


@dataclass
class MetricsSummary:
    """Aggregated metrics summary."""
    period: str  # "daily", "hourly"
    start_time: str
    end_time: str

    # Investigation counts
    total_investigations: int = 0
    successful: int = 0
    failed: int = 0

    # Classification distribution
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    cleared_count: int = 0

    # Downgrades
    total_downgrades: int = 0
    downgrade_reasons: Dict[str, int] = field(default_factory=dict)

    # Performance
    avg_latency_ms: float = 0
    p95_latency_ms: float = 0
    avg_tool_calls: float = 0
    avg_llm_calls: float = 0

    # Errors
    error_rate: float = 0
    error_types: Dict[str, int] = field(default_factory=dict)


def analyze_traces(log_file: Path) -> MetricsSummary:
    """Analyze a trace log file and return metrics summary."""
    traces = []

    with open(log_file) as f:
        for line in f:
            if line.strip():
                traces.append(json.loads(line))

    if not traces:
        return MetricsSummary(
            period="daily",
            start_time="",
            end_time=""
        )

    # Calculate metrics
    summary = MetricsSummary(
        period="daily",
        start_time=traces[0].get("timestamp", ""),
        end_time=traces[-1].get("timestamp", ""),
        total_investigations=len(traces)
    )

    latencies = []
    tool_call_counts = []
    llm_call_counts = []

    for trace in traces:
        # Success/failure
        if trace.get("success", True):
            summary.successful += 1
        else:
            summary.failed += 1
            error = trace.get("error", "unknown")
            summary.error_types[error] = summary.error_types.get(error, 0) + 1

        # Classification distribution
        classification = trace.get("classification", "").upper()
        if classification == "HIGH":
            summary.high_count += 1
        elif classification == "MEDIUM":
            summary.medium_count += 1
        elif classification == "LOW":
            summary.low_count += 1
        elif classification == "CLEARED":
            summary.cleared_count += 1

        # Downgrades
        if trace.get("downgraded"):
            summary.total_downgrades += 1
            reason = trace.get("downgrade_reason", "unknown")
            summary.downgrade_reasons[reason] = summary.downgrade_reasons.get(reason, 0) + 1

        # Performance
        latencies.append(trace.get("total_latency_ms", 0))
        tool_call_counts.append(len(trace.get("tool_calls", [])))
        llm_call_counts.append(len(trace.get("llm_calls", [])))

    # Aggregate performance metrics
    if latencies:
        summary.avg_latency_ms = sum(latencies) / len(latencies)
        sorted_latencies = sorted(latencies)
        p95_idx = int(len(sorted_latencies) * 0.95)
        summary.p95_latency_ms = sorted_latencies[p95_idx] if p95_idx < len(sorted_latencies) else sorted_latencies[-1]

    if tool_call_counts:
        summary.avg_tool_calls = sum(tool_call_counts) / len(tool_call_counts)

    if llm_call_counts:
        summary.avg_llm_calls = sum(llm_call_counts) / len(llm_call_counts)

    summary.error_rate = summary.failed / summary.total_investigations if summary.total_investigations > 0 else 0

    return summary


def print_metrics_dashboard(summary: MetricsSummary):
    """Print a formatted metrics dashboard."""
    print(f"""
{'='*70}
MEDIGRAPH OBSERVABILITY DASHBOARD
Period: {summary.start_time} to {summary.end_time}
{'='*70}

INVESTIGATIONS
  Total: {summary.total_investigations}
  Successful: {summary.successful}
  Failed: {summary.failed}
  Error Rate: {summary.error_rate:.1%}

CLASSIFICATIONS
  HIGH: {summary.high_count}
  MEDIUM: {summary.medium_count}
  LOW: {summary.low_count}
  CLEARED: {summary.cleared_count}

DOWNGRADES
  Total: {summary.total_downgrades}
  Reasons: {summary.downgrade_reasons}

PERFORMANCE
  Avg Latency: {summary.avg_latency_ms:.0f}ms
  P95 Latency: {summary.p95_latency_ms:.0f}ms
  Avg Tool Calls: {summary.avg_tool_calls:.1f}
  Avg LLM Calls: {summary.avg_llm_calls:.1f}

{'='*70}
""")
