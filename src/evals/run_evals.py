#!/usr/bin/env python3
"""
MediGraph Evaluation Runner

Runs classification evaluations against the golden set and reports metrics.

Usage:
    # Run all evaluations
    python -m src.evals.run_evals

    # Run classification eval only
    python -m src.evals.run_evals --classification

    # Run factual accuracy on saved dossiers
    python -m src.evals.run_evals --factual

    # Show observability dashboard
    python -m src.evals.run_evals --dashboard
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List

from .golden_set import GOLDEN_SET
from .factual_accuracy import FactualAccuracyChecker, print_accuracy_report
from .observability import analyze_traces, print_metrics_dashboard, LOG_DIR


# Import agent tools
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from src.agent.tools.red_flag_tools import check_red_flags
    TOOLS_AVAILABLE = True
except ImportError:
    TOOLS_AVAILABLE = False
    print("Warning: Agent tools not available. Some evals will be skipped.")


@dataclass
class ClassificationResult:
    """Result of a single classification evaluation."""
    community_id: int
    expected_class: str
    expected_label: str
    actual_label: str
    passed: bool
    downgraded: bool
    fp_warnings: int
    reason: str


def evaluate_classification(entry: dict) -> ClassificationResult:
    """Evaluate classification for a single golden set entry."""
    community_id = entry["community_id"]
    expected_class = entry["expected_class"]
    expected_label = entry["expected_label"]
    reason = entry["reason"]

    # Get actual classification
    result = check_red_flags(community_id)
    actual_label = result["risk_label"]
    classification_note = result.get("classification_note", "")
    fp_warnings = len(result.get("false_positive_warnings", []))

    # Distinguish between "downgraded from HIGH" and "upgraded due to fraud density"
    downgraded = "Downgraded" in classification_note
    fraud_density_override = "fraud_density" in classification_note.lower() or "exclusion rate" in classification_note.lower()

    # Determine if passed
    if expected_class == "FALSE_POSITIVE":
        # Should be downgraded or low/medium
        passed = actual_label in ["LOW", "MEDIUM"] or downgraded
    elif expected_class == "CONFIRMED_FRAUD":
        # Should be HIGH - either via flags or fraud density override
        # The fraud density override is acceptable (it's not a "downgrade")
        passed = actual_label == "HIGH"
    elif expected_class == "SUSPICIOUS":
        # Should be MEDIUM or HIGH
        passed = actual_label in ["MEDIUM", "HIGH"]
    elif expected_class == "CLEARED":
        # Should be LOW
        passed = actual_label == "LOW"
    else:
        passed = actual_label == expected_label

    return ClassificationResult(
        community_id=community_id,
        expected_class=expected_class,
        expected_label=expected_label,
        actual_label=actual_label,
        passed=passed,
        downgraded=downgraded,
        fp_warnings=fp_warnings,
        reason=reason
    )


def run_classification_eval() -> List[ClassificationResult]:
    """Run classification evaluation on golden set."""
    print("\n" + "=" * 70)
    print("CLASSIFICATION EVALUATION - Golden Set")
    print("=" * 70)

    results = []

    for entry in GOLDEN_SET:
        result = evaluate_classification(entry)
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        print(f"\n[{status}] Community {result.community_id}")
        print(f"  Expected: {result.expected_class} ({result.expected_label})")
        print(f"  Actual: {result.actual_label}")
        print(f"  Downgraded: {result.downgraded}")
        print(f"  FP Warnings: {result.fp_warnings}")
        print(f"  Reason: {result.reason}")

    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    accuracy = passed / total if total > 0 else 0

    print("\n" + "-" * 70)
    print(f"SUMMARY: {passed}/{total} passed ({accuracy:.1%})")
    print("-" * 70)

    # Breakdown by expected class
    for expected_class in ["FALSE_POSITIVE", "CONFIRMED_FRAUD", "SUSPICIOUS", "CLEARED"]:
        class_results = [r for r in results if r.expected_class == expected_class]
        class_passed = sum(1 for r in class_results if r.passed)
        if class_results:
            print(f"  {expected_class}: {class_passed}/{len(class_results)}")

    print("=" * 70 + "\n")

    return results


def run_factual_accuracy_eval():
    """Run factual accuracy evaluation on saved dossiers."""
    print("\n" + "=" * 70)
    print("FACTUAL ACCURACY EVALUATION")
    print("=" * 70)

    outputs_dir = Path(__file__).parent.parent.parent.parent / "outputs"

    if not outputs_dir.exists():
        print("No outputs directory found. Run investigations first.")
        return

    dossier_files = list(outputs_dir.glob("dossier_*.json"))

    if not dossier_files:
        print("No dossier files found.")
        return

    print(f"Found {len(dossier_files)} dossier files\n")

    checker = FactualAccuracyChecker()
    total_claims = 0
    total_verified = 0
    all_errors = []

    for dossier_file in dossier_files:
        try:
            with open(dossier_file) as f:
                dossier = json.load(f)

            result = checker.evaluate_dossier(dossier)
            total_claims += result.total_claims
            total_verified += result.verified_claims
            all_errors.extend(result.errors)

            status = "PASS" if result.accuracy >= 0.95 else "WARN" if result.accuracy >= 0.8 else "FAIL"
            print(f"[{status}] {dossier_file.name}: {result.accuracy:.1%} ({result.verified_claims}/{result.total_claims})")

        except Exception as e:
            print(f"[ERROR] {dossier_file.name}: {e}")

    # Summary
    overall_accuracy = total_verified / total_claims if total_claims > 0 else 1.0

    print("\n" + "-" * 70)
    print(f"OVERALL FACTUAL ACCURACY: {overall_accuracy:.1%}")
    print(f"Total Claims: {total_claims}")
    print(f"Verified: {total_verified}")
    print(f"Failed: {total_claims - total_verified}")

    if all_errors:
        print(f"\nSample Errors:")
        for error in all_errors[:5]:
            print(f"  - {error}")

    print("=" * 70 + "\n")


def run_observability_dashboard():
    """Show observability dashboard from trace logs."""
    print("\n" + "=" * 70)
    print("OBSERVABILITY DASHBOARD")
    print("=" * 70)

    if not LOG_DIR.exists():
        print("No logs directory found. Run investigations with tracing enabled first.")
        return

    # Find most recent trace file
    trace_files = list(LOG_DIR.glob("traces_*.jsonl"))

    if not trace_files:
        print("No trace files found.")
        return

    # Analyze most recent
    latest_trace = sorted(trace_files)[-1]
    print(f"Analyzing: {latest_trace.name}")

    summary = analyze_traces(latest_trace)
    print_metrics_dashboard(summary)


def save_eval_report(results: List[ClassificationResult], output_path: Path):
    """Save evaluation results to JSON."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "accuracy": sum(1 for r in results if r.passed) / len(results) if results else 0,
        "results": [
            {
                "community_id": r.community_id,
                "expected_class": r.expected_class,
                "expected_label": r.expected_label,
                "actual_label": r.actual_label,
                "passed": r.passed,
                "downgraded": r.downgraded,
                "fp_warnings": r.fp_warnings,
                "reason": r.reason
            }
            for r in results
        ]
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="MediGraph Evaluation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--classification", "-c",
        action="store_true",
        help="Run classification evaluation on golden set"
    )
    parser.add_argument(
        "--factual", "-f",
        action="store_true",
        help="Run factual accuracy evaluation on saved dossiers"
    )
    parser.add_argument(
        "--dashboard", "-d",
        action="store_true",
        help="Show observability dashboard"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Run all evaluations"
    )
    parser.add_argument(
        "--save",
        type=str,
        help="Save evaluation report to specified path"
    )

    args = parser.parse_args()

    # Default to all if no specific eval selected
    run_all = args.all or not (args.classification or args.factual or args.dashboard)

    results = []

    if args.classification or run_all:
        if TOOLS_AVAILABLE:
            results = run_classification_eval()
        else:
            print("Skipping classification eval - tools not available")

    if args.factual or run_all:
        run_factual_accuracy_eval()

    if args.dashboard or run_all:
        run_observability_dashboard()

    if args.save and results:
        save_eval_report(results, Path(args.save))


if __name__ == "__main__":
    main()
