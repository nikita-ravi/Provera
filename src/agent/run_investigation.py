#!/usr/bin/env python3
"""
MediGraph Investigation Agent CLI

Usage:
    # List top 10 riskiest communities (statewide)
    python -m src.agent.run_investigation --top 10

    # Filter by region (city name, case-insensitive)
    python -m src.agent.run_investigation --region "MIAMI" --top 10

    # Filter by ZIP prefix
    python -m src.agent.run_investigation --zip "331" --top 10

    # Investigate a specific community (Louvain-based)
    python -m src.agent.run_investigation --community 47

    # Investigate the top 5 riskiest communities
    python -m src.agent.run_investigation --investigate-top 5

    # Investigate a specific NPI using ego network expansion (2 hops)
    python -m src.agent.run_investigation --npi 1234567890

    # Investigate with custom hop distance
    python -m src.agent.run_investigation --npi 1234567890 --hops 3
"""
import argparse
import json
from datetime import datetime

from .orchestrator import FraudInvestigator


def print_ego_dossier(dossier: dict):
    """Pretty print an ego network dossier."""
    print("\n" + "=" * 70)
    print(f"EGO NETWORK INVESTIGATION — Seed NPI {dossier['seed_npi']}")
    print(f"Seed Facility: {dossier['seed_name']}")
    print("=" * 70)

    print(f"\nClassification: {dossier['classification']}")
    print(f"Red Flags: {dossier['flags_triggered']}/{dossier['total_flags']}")
    print(f"Cluster Size: {dossier['member_count']} facilities ({dossier['hops']}-hop expansion)")
    print(f"Excluded: {dossier['excluded_count']}")
    print(f"Avg Risk Score: {dossier['avg_risk_score']:.3f}")

    # Show hop distribution
    hop_dist = dossier.get("hop_distribution", {})
    if hop_dist:
        print(f"Hop Distribution: {dict(hop_dist)}")

    if dossier.get("hypotheses"):
        print("\n" + "-" * 40)
        print("HYPOTHESES")
        print("-" * 40)
        print(dossier["hypotheses"])

    if dossier.get("evaluation"):
        print("\n" + "-" * 40)
        print("EVALUATION")
        print("-" * 40)
        print(dossier["evaluation"])

    if dossier.get("narrative"):
        print("\n" + "-" * 40)
        print("DOSSIER")
        print("-" * 40)
        print(dossier["narrative"])

    print("\n" + "=" * 70)


def print_dossier(dossier: dict):
    """Pretty print a dossier."""
    print("\n" + "=" * 70)
    print(f"INVESTIGATION DOSSIER — Community {dossier['community_id']}")
    print("=" * 70)

    print(f"\nClassification: {dossier['classification']}")
    print(f"Red Flags: {dossier['flags_triggered']}/{dossier['total_flags']}")
    print(f"Members: {dossier['member_count']}")
    print(f"Excluded: {dossier['excluded_count']}")
    print(f"Avg Risk Score: {dossier['avg_risk_score']:.3f}")

    if dossier.get("hypotheses"):
        print("\n" + "-" * 40)
        print("HYPOTHESES")
        print("-" * 40)
        print(dossier["hypotheses"])

    if dossier.get("evaluation"):
        print("\n" + "-" * 40)
        print("EVALUATION")
        print("-" * 40)
        print(dossier["evaluation"])

    if dossier.get("narrative"):
        print("\n" + "-" * 40)
        print("DOSSIER")
        print("-" * 40)
        print(dossier["narrative"])

    print("\n" + "=" * 70)


def print_community_list(communities: list, region: str = None, zip_prefix: str = None):
    """Print a table of communities."""
    print("\n" + "=" * 80)
    if region:
        print(f"TOP RISK COMMUNITIES — Region: {region.upper()}")
    elif zip_prefix:
        print(f"TOP RISK COMMUNITIES — ZIP prefix: {zip_prefix}")
    else:
        print("TOP RISK COMMUNITIES — Statewide")
    print("=" * 80)
    print(f"{'ID':>8} {'Members':>8} {'Excluded':>8} {'Avg Risk':>10} {'Max Risk':>10} {'Density':>10}")
    print("-" * 80)

    for c in communities:
        print(
            f"{c['community_id']:>8} "
            f"{c['member_count']:>8} "
            f"{c['excluded_count']:>8} "
            f"{c['avg_risk_score']:>10.3f} "
            f"{c['max_risk_score']:>10.3f} "
            f"{c['fraud_density']:>10.1%}"
        )

    print("=" * 80)


def save_dossier(dossier: dict, output_dir: str = "outputs"):
    """Save dossier to JSON file."""
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Handle both community and ego network dossiers
    if "community_id" in dossier:
        filename = f"dossier_community_{dossier['community_id']}_{timestamp}.json"
    else:
        filename = f"dossier_ego_{dossier['seed_npi']}_{timestamp}.json"

    with open(output_path / filename, "w") as f:
        json.dump(dossier, f, indent=2, default=str)

    print(f"\nDossier saved to: {output_path / filename}")


def main():
    """Run investigation on a community or list top-risk communities."""
    parser = argparse.ArgumentParser(
        description="MediGraph Fraud Investigation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Statewide screening
  python -m src.agent.run_investigation --top 10

  # Geographic screening
  python -m src.agent.run_investigation --region "MIAMI" --top 10
  python -m src.agent.run_investigation --zip "331" --top 10

  # Community investigation
  python -m src.agent.run_investigation --community 47
  python -m src.agent.run_investigation --investigate-top 3

  # NPI investigation (ego network)
  python -m src.agent.run_investigation --npi 1234567890
  python -m src.agent.run_investigation --npi 1234567890 --hops 3
        """
    )
    parser.add_argument(
        "--npi", "-n",
        type=str,
        help="Investigate a specific NPI using ego network expansion"
    )
    parser.add_argument(
        "--hops",
        type=int,
        default=2,
        help="Number of hops for ego network expansion (default: 2)"
    )
    parser.add_argument(
        "--community", "-c",
        type=int,
        help="Investigate a specific community ID (Louvain-based)"
    )
    parser.add_argument(
        "--top", "-t",
        type=int,
        default=10,
        help="Show top N risk communities (default: 10)"
    )
    parser.add_argument(
        "--region", "-r",
        type=str,
        help="Filter by city/region name (case-insensitive match on address)"
    )
    parser.add_argument(
        "--zip", "-z",
        type=str,
        help="Filter by ZIP code prefix (e.g., '331' for Miami area)"
    )
    parser.add_argument(
        "--investigate-top", "-i",
        type=int,
        help="Investigate the top N riskiest communities"
    )
    parser.add_argument(
        "--min-size", "-m",
        type=int,
        default=3,
        help="Minimum community size to consider (default: 3)"
    )
    parser.add_argument(
        "--save", "-s",
        action="store_true",
        help="Save dossier to JSON file"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="outputs",
        help="Output directory for saved dossiers (default: outputs)"
    )

    args = parser.parse_args()

    investigator = FraudInvestigator()

    if args.npi:
        # Ego network investigation mode
        print(f"\nInvestigating NPI {args.npi} via {args.hops}-hop ego network expansion...")
        dossier = investigator.investigate_npi(args.npi, hops=args.hops)

        if "error" in dossier:
            print(f"Error: {dossier['error']}")
            return

        print_ego_dossier(dossier)

        if args.save:
            save_dossier(dossier, args.output_dir)

    elif args.community:
        # Investigate a specific community
        print(f"\nInvestigating community {args.community}...")
        dossier = investigator.investigate_community(args.community)

        if "error" in dossier:
            print(f"Error: {dossier['error']}")
            return

        print_dossier(dossier)

        if args.save:
            save_dossier(dossier, args.output_dir)

    elif args.investigate_top:
        # Investigate top N communities
        top = investigator.list_top_communities(
            n=args.investigate_top,
            min_size=args.min_size,
            region=args.region,
            zip_prefix=args.zip
        )

        if args.region or args.zip:
            filter_desc = f"region '{args.region}'" if args.region else f"ZIP '{args.zip}'"
            print(f"\nFiltered to {filter_desc}")

        for i, community in enumerate(top):
            print(f"\n[{i+1}/{len(top)}] Investigating community {community['community_id']}...")
            dossier = investigator.investigate_community(community["community_id"])

            if "error" in dossier:
                print(f"Error: {dossier['error']}")
                continue

            print_dossier(dossier)

            if args.save:
                save_dossier(dossier, args.output_dir)

            print("\n" + "=" * 70 + "\n")

    else:
        # List top communities (with optional geographic filter)
        top = investigator.list_top_communities(
            n=args.top,
            min_size=args.min_size,
            region=args.region,
            zip_prefix=args.zip
        )
        print_community_list(top, region=args.region, zip_prefix=args.zip)


if __name__ == "__main__":
    main()
