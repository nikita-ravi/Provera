#!/usr/bin/env python3
"""
Evaluate agent factual accuracy on a sample of communities.

Usage:
    export ANTHROPIC_API_KEY="your-key-here"
    python -m src.agent.evaluate_agent
"""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

from .orchestrator import FraudInvestigator
from .tools.graph_tools import get_community_members, get_top_risk_communities
from .tools.red_flag_tools import check_red_flags
from .tools.facility_tools import get_facility_profile


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "medigraph" / "outputs"


def verify_dossier_claims(dossier: dict) -> dict:
    """
    Verify factual claims in a dossier against source data.

    Returns: {
        "community_id": int,
        "total_claims": int,
        "verified_claims": int,
        "accuracy": float,
        "errors": list,
    }
    """
    community_id = dossier["community_id"]
    errors = []
    verified = 0
    total = 0

    # Verify member count
    total += 1
    actual_members = len(get_community_members(community_id))
    if dossier["member_count"] == actual_members:
        verified += 1
    else:
        errors.append(f"Member count: claimed {dossier['member_count']}, actual {actual_members}")

    # Verify excluded count
    total += 1
    actual_excluded = dossier["excluded_count"]
    members = get_community_members(community_id)
    real_excluded = sum(1 for m in members if m["is_excluded"])
    if actual_excluded == real_excluded:
        verified += 1
    else:
        errors.append(f"Excluded count: claimed {actual_excluded}, actual {real_excluded}")

    # Verify red flags count
    total += 1
    red_flags = check_red_flags(community_id)
    if dossier["flags_triggered"] == red_flags["flags_triggered"]:
        verified += 1
    else:
        errors.append(f"Flags: claimed {dossier['flags_triggered']}, actual {red_flags['flags_triggered']}")

    # Verify each member exists and has correct risk score
    for member in dossier.get("members", [])[:10]:  # Check first 10
        total += 1
        profile = get_facility_profile(member["npi"])
        if "error" in profile:
            errors.append(f"NPI {member['npi']}: not found in data")
        elif abs(profile["fraud_risk_score"] - member["fraud_risk_score"]) < 0.001:
            verified += 1
        else:
            errors.append(
                f"NPI {member['npi']} risk: claimed {member['fraud_risk_score']:.3f}, "
                f"actual {profile['fraud_risk_score']:.3f}"
            )

    accuracy = verified / total if total > 0 else 0

    return {
        "community_id": community_id,
        "total_claims": total,
        "verified_claims": verified,
        "accuracy": accuracy,
        "errors": errors,
    }


def evaluate_agent(n_high: int = 3, n_medium: int = 2, n_cleared: int = 2) -> pd.DataFrame:
    """
    Evaluate agent on a mix of high, medium, and cleared communities.

    Args:
        n_high: Number of HIGH risk communities to evaluate
        n_medium: Number of MEDIUM risk communities
        n_cleared: Number of CLEARED communities

    Returns:
        DataFrame with evaluation results
    """
    print("=" * 70)
    print("AGENT EVALUATION")
    print("=" * 70)

    investigator = FraudInvestigator()

    # Get communities to evaluate (larger pool to find all HIGH communities)
    top = get_top_risk_communities(n=50, min_size=3)

    # Categorize by red flags
    high_risk = []
    medium_risk = []

    for c in top:
        rf = check_red_flags(c["community_id"])
        if rf["risk_label"] == "HIGH":
            high_risk.append(c)
        elif rf["risk_label"] == "MEDIUM":
            medium_risk.append(c)

    # Find cleared communities (low risk, no exclusions, AND 0 red flags)
    from .tools.graph_tools import _load_features
    df = _load_features()
    low_risk_comms = df.groupby('louvain_community').agg({
        'fraud_risk_score': 'mean',
        'is_excluded': 'sum',
        'npi': 'count'
    }).reset_index()
    low_risk_comms = low_risk_comms[
        (low_risk_comms['fraud_risk_score'] < 0.3) &
        (low_risk_comms['is_excluded'] == 0) &
        (low_risk_comms['npi'] >= 3)
    ].sort_values('fraud_risk_score')

    # Filter to only communities with 0 red flags (will be CLEARED by agent)
    cleared = []
    for _, row in low_risk_comms.iterrows():
        comm_id = int(row['louvain_community'])
        rf = check_red_flags(comm_id)
        if rf["flags_triggered"] == 0:
            cleared.append({"community_id": comm_id})
            if len(cleared) >= n_cleared:
                break

    # Select communities to evaluate
    to_evaluate = (
        high_risk[:n_high] +
        medium_risk[:n_medium] +
        cleared
    )

    print(f"\nEvaluating {len(to_evaluate)} communities:")
    print(f"  HIGH risk: {min(n_high, len(high_risk))}")
    print(f"  MEDIUM risk: {min(n_medium, len(medium_risk))}")
    print(f"  CLEARED: {len(cleared)}")

    results = []

    for i, comm in enumerate(to_evaluate):
        community_id = comm["community_id"]
        print(f"\n[{i+1}/{len(to_evaluate)}] Investigating community {community_id}...")

        try:
            dossier = investigator.investigate_community(community_id)

            if "error" in dossier:
                print(f"  Error: {dossier['error']}")
                continue

            # Verify claims
            verification = verify_dossier_claims(dossier)

            results.append({
                "community_id": community_id,
                "classification": dossier["classification"],
                "total_claims": verification["total_claims"],
                "verified_claims": verification["verified_claims"],
                "accuracy": verification["accuracy"],
                "notes": "; ".join(verification["errors"][:3]) if verification["errors"] else "All claims verified"
            })

            print(f"  Classification: {dossier['classification']}")
            print(f"  Accuracy: {verification['accuracy']:.1%} ({verification['verified_claims']}/{verification['total_claims']})")

            if verification["errors"]:
                print(f"  Errors: {verification['errors'][0]}")

        except Exception as e:
            print(f"  Exception: {e}")
            results.append({
                "community_id": community_id,
                "classification": "ERROR",
                "total_claims": 0,
                "verified_claims": 0,
                "accuracy": 0,
                "notes": str(e)
            })

    # Create results DataFrame
    results_df = pd.DataFrame(results)

    # Save results
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUTS_DIR / "agent_evaluation.csv"
    results_df.to_csv(output_path, index=False)

    # Print summary
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"\nTotal communities evaluated: {len(results_df)}")

    if len(results_df) > 0:
        avg_accuracy = results_df["accuracy"].mean()
        print(f"Average accuracy: {avg_accuracy:.1%}")
        print(f"Communities with 100% accuracy: {(results_df['accuracy'] == 1.0).sum()}")
        print(f"Communities with >95% accuracy: {(results_df['accuracy'] >= 0.95).sum()}")

    print(f"\nResults saved to: {output_path}")

    return results_df


def main():
    """Run agent evaluation."""
    import argparse
    parser = argparse.ArgumentParser(description="Evaluate MediGraph agent accuracy")
    parser.add_argument("--high", type=int, default=3, help="Number of HIGH risk communities")
    parser.add_argument("--medium", type=int, default=2, help="Number of MEDIUM risk communities")
    parser.add_argument("--cleared", type=int, default=2, help="Number of CLEARED communities")

    args = parser.parse_args()

    results = evaluate_agent(n_high=args.high, n_medium=args.medium, n_cleared=args.cleared)

    return results


if __name__ == "__main__":
    main()
