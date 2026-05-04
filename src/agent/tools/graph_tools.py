"""Graph traversal tools."""
import pickle
import pandas as pd
import networkx as nx
from pathlib import Path
from functools import lru_cache
from collections import Counter

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@lru_cache(maxsize=1)
def _load_features() -> pd.DataFrame:
    """Load facility features merged with names (cached)."""
    features = pd.read_parquet(PROCESSED_DIR / "facility_features.parquet")
    master = pd.read_parquet(PROCESSED_DIR / "master_facilities.parquet")

    # Merge facility names from master
    features = features.merge(
        master[["npi", "facility_name"]],
        on="npi",
        how="left",
        suffixes=("", "_master")
    )

    # Use master name if not in features
    if "facility_name_master" in features.columns:
        features["facility_name"] = features["facility_name_master"]
        features = features.drop(columns=["facility_name_master"])

    return features


@lru_cache(maxsize=1)
def _load_graph() -> nx.Graph:
    """Load heterogeneous graph (cached)."""
    with open(PROCESSED_DIR / "medigraph.gpickle", "rb") as f:
        return pickle.load(f)


@lru_cache(maxsize=1)
def _load_facility_graph() -> nx.Graph:
    """Load facility-only projection (cached)."""
    with open(PROCESSED_DIR / "facility_graph.gpickle", "rb") as f:
        return pickle.load(f)


def get_community_members(community_id: int) -> list:
    """
    Returns all facilities in a Louvain community.

    Output: list of {
        "npi": str,
        "facility_name": str,
        "fraud_risk_score": float,
        "is_excluded": bool,
        "provider_type": str,
    }
    Sorted by fraud_risk_score descending.
    """
    df = _load_features()

    members = df[df["louvain_community"] == community_id].copy()

    if members.empty:
        return []

    # Sort by risk score descending
    members = members.sort_values("fraud_risk_score", ascending=False)

    result = []
    for _, row in members.iterrows():
        result.append({
            "npi": str(row["npi"]),
            "facility_name": str(row.get("facility_name", "Unknown")) if pd.notna(row.get("facility_name")) else "Unknown",
            "fraud_risk_score": float(row["fraud_risk_score"]),
            "is_excluded": bool(row["is_excluded"]),
            "provider_type": str(row.get("provider_type", "Unknown")),
        })

    return result


def get_community_stats(community_id: int) -> dict:
    """
    Returns aggregate statistics for a community.

    Output: {
        "community_id": int,
        "member_count": int,
        "avg_risk_score": float,
        "max_risk_score": float,
        "excluded_count": int,
        "fraud_density": float,
        "snf_count": int,
        "hha_count": int,
        "unique_owners": int,
        "unique_addresses": int,
    }
    """
    df = _load_features()
    G = _load_graph()

    members = df[df["louvain_community"] == community_id]

    if members.empty:
        return {"error": f"Community {community_id} not found"}

    member_count = len(members)
    excluded_count = int(members["is_excluded"].sum())

    # Get unique owners for members
    ownership = pd.read_parquet(PROCESSED_DIR / "master_ownership.parquet")
    member_npis = set(members["npi"].astype(str))
    member_ownership = ownership[ownership["facility_npi"].astype(str).isin(member_npis)]
    unique_owners = member_ownership["owner_normalized_name"].nunique()

    # Get unique addresses
    unique_addresses = 0
    for npi in member_npis:
        facility_node = f"facility:{npi}"
        if facility_node in G:
            addr = G.nodes[facility_node].get("normalized_address", "")
            if addr:
                unique_addresses += 1

    # Count by type
    snf_count = int((members["provider_type"] == "SNF").sum())
    hha_count = int((members["provider_type"] == "HHA").sum())

    return {
        "community_id": int(community_id),
        "member_count": member_count,
        "avg_risk_score": float(members["fraud_risk_score"].mean()),
        "max_risk_score": float(members["fraud_risk_score"].max()),
        "excluded_count": excluded_count,
        "fraud_density": excluded_count / member_count if member_count > 0 else 0.0,
        "snf_count": snf_count,
        "hha_count": hha_count,
        "unique_owners": unique_owners,
        "unique_addresses": unique_addresses,
    }


def get_neighbors(npi: str, edge_type: str = None) -> list:
    """
    Returns facilities connected to this one in the facility graph.
    Optionally filter by edge type: SHARES_OWNER, SHARES_ADDRESS, SHARES_PHONE

    Output: list of {
        "npi": str,
        "facility_name": str,
        "connection_type": str,
        "fraud_risk_score": float,
        "is_excluded": bool,
    }
    """
    F = _load_facility_graph()
    df = _load_features()

    facility_node = f"facility:{npi}"

    if facility_node not in F:
        return []

    result = []
    for neighbor in F.neighbors(facility_node):
        neighbor_npi = neighbor.replace("facility:", "")

        # Get edge data
        edge_data = F.get_edge_data(facility_node, neighbor, {})

        connection_types = []
        if edge_data.get("shared_owners", 0) > 0:
            connection_types.append("SHARES_OWNER")
        if edge_data.get("shared_addresses", 0) > 0:
            connection_types.append("SHARES_ADDRESS")
        if edge_data.get("shared_phones", 0) > 0:
            connection_types.append("SHARES_PHONE")

        if not connection_types:
            # Infer from weight
            if edge_data.get("weight", 0) > 0:
                connection_types.append("CONNECTED")

        connection_type = ", ".join(connection_types) if connection_types else "UNKNOWN"

        # Filter by edge type if specified
        if edge_type and edge_type not in connection_type:
            continue

        # Get facility info
        facility_row = df[df["npi"].astype(str) == neighbor_npi]
        if facility_row.empty:
            continue

        row = facility_row.iloc[0]

        result.append({
            "npi": neighbor_npi,
            "facility_name": str(row.get("facility_name", "Unknown")) if pd.notna(row.get("facility_name")) else "Unknown",
            "connection_type": connection_type,
            "fraud_risk_score": float(row["fraud_risk_score"]),
            "is_excluded": bool(row["is_excluded"]),
        })

    # Sort by risk score
    result.sort(key=lambda x: x["fraud_risk_score"], reverse=True)

    return result


def ego_network_expand(seed_npi: str, hops: int = 2) -> list:
    """
    Expands outward from a seed NPI through ownership, address, and phone edges.

    This is the ego network approach: instead of relying on global Louvain communities,
    we dynamically build a cluster by starting from a specific facility and finding
    everything reachable within k hops.

    Args:
        seed_npi: The NPI to start from
        hops: Maximum number of hops to expand (default: 2)

    Output: list of {
        "npi": str,
        "facility_name": str,
        "fraud_risk_score": float,
        "is_excluded": bool,
        "provider_type": str,
        "hop_distance": int,  # 0 = seed, 1 = direct neighbor, 2 = neighbor of neighbor
        "connection_path": str,  # How this facility connects to the seed
    }
    Sorted by hop_distance ascending, then fraud_risk_score descending.
    """
    F = _load_facility_graph()
    df = _load_features()

    seed_node = f"facility:{seed_npi}"

    if seed_node not in F:
        return []

    # Use NetworkX's single_source_shortest_path_length for efficient k-hop expansion
    distances = nx.single_source_shortest_path_length(F, seed_node, cutoff=hops)

    result = []
    for node, distance in distances.items():
        npi = node.replace("facility:", "")

        # Get facility info from features
        facility_row = df[df["npi"].astype(str) == npi]
        if facility_row.empty:
            continue

        row = facility_row.iloc[0]

        # Determine connection path for non-seed nodes
        connection_path = ""
        if distance > 0:
            # Find how this node connects to seed (via which edge types)
            if distance == 1:
                edge_data = F.get_edge_data(seed_node, node, {})
                paths = []
                if edge_data.get("shared_owners", 0) > 0:
                    paths.append("shared_owner")
                if edge_data.get("shared_addresses", 0) > 0:
                    paths.append("shared_address")
                if edge_data.get("shared_phones", 0) > 0:
                    paths.append("shared_phone")
                connection_path = ", ".join(paths) if paths else "connected"
            else:
                # For 2+ hops, just indicate it's indirect
                connection_path = f"{distance}-hop indirect"

        result.append({
            "npi": npi,
            "facility_name": str(row.get("facility_name", "Unknown")) if pd.notna(row.get("facility_name")) else "Unknown",
            "fraud_risk_score": float(row["fraud_risk_score"]),
            "is_excluded": bool(row["is_excluded"]),
            "provider_type": str(row.get("provider_type", "Unknown")),
            "hop_distance": distance,
            "connection_path": connection_path,
        })

    # Sort by hop distance (seed first), then by risk score descending
    result.sort(key=lambda x: (x["hop_distance"], -x["fraud_risk_score"]))

    return result


def get_ego_cluster_stats(seed_npi: str, hops: int = 2) -> dict:
    """
    Returns aggregate statistics for an ego network cluster.

    Similar to get_community_stats but for dynamically-built ego networks.

    Output: {
        "seed_npi": str,
        "seed_name": str,
        "hops": int,
        "member_count": int,
        "avg_risk_score": float,
        "max_risk_score": float,
        "excluded_count": int,
        "fraud_density": float,
        "snf_count": int,
        "hha_count": int,
        "unique_owners": int,
        "hop_distribution": dict,  # {0: 1, 1: N, 2: M}
    }
    """
    members = ego_network_expand(seed_npi, hops)

    if not members:
        return {"error": f"NPI {seed_npi} not found in graph"}

    # Find seed info
    seed_member = next((m for m in members if m["hop_distance"] == 0), None)
    seed_name = seed_member["facility_name"] if seed_member else "Unknown"

    member_count = len(members)
    excluded_count = sum(1 for m in members if m["is_excluded"])
    snf_count = sum(1 for m in members if m["provider_type"] == "SNF")
    hha_count = sum(1 for m in members if m["provider_type"] == "HHA")

    risk_scores = [m["fraud_risk_score"] for m in members]

    # Hop distribution
    hop_distribution = Counter(m["hop_distance"] for m in members)

    # Get unique owners
    ownership = pd.read_parquet(PROCESSED_DIR / "master_ownership.parquet")
    member_npis = set(m["npi"] for m in members)
    member_ownership = ownership[ownership["facility_npi"].astype(str).isin(member_npis)]
    unique_owners = member_ownership["owner_normalized_name"].nunique()

    return {
        "seed_npi": seed_npi,
        "seed_name": seed_name,
        "hops": hops,
        "member_count": member_count,
        "avg_risk_score": sum(risk_scores) / len(risk_scores) if risk_scores else 0.0,
        "max_risk_score": max(risk_scores) if risk_scores else 0.0,
        "excluded_count": excluded_count,
        "fraud_density": excluded_count / member_count if member_count > 0 else 0.0,
        "snf_count": snf_count,
        "hha_count": hha_count,
        "unique_owners": unique_owners,
        "hop_distribution": dict(hop_distribution),
    }


def get_top_risk_communities(
    n: int = 10,
    min_size: int = 3,
    region: str = None,
    zip_prefix: str = None
) -> list:
    """
    Returns the top N communities ranked by average fraud risk score.
    Only includes communities with at least min_size members.

    Args:
        n: Number of top communities to return
        min_size: Minimum community size to consider
        region: Filter by city/region name (case-insensitive match on address)
        zip_prefix: Filter by ZIP code prefix

    Output: list of community_stats dicts
    """
    df = _load_features()

    # Apply geographic filtering if specified
    if region or zip_prefix:
        # Load master facilities to get address info
        master = pd.read_parquet(PROCESSED_DIR / "master_facilities.parquet")

        # Merge address info
        df = df.merge(
            master[["npi", "address"]],
            on="npi",
            how="left",
            suffixes=("", "_master")
        )

        if region:
            # Case-insensitive city/region match on address
            region_upper = region.upper()
            df = df[df["address"].str.upper().str.contains(region_upper, na=False)]

        if zip_prefix:
            # Extract ZIP from address (typically at end) and match prefix
            # ZIP codes in Florida addresses are typically 5 digits at the end
            import re
            def extract_zip(addr):
                if pd.isna(addr):
                    return ""
                match = re.search(r'\b(\d{5})(?:-\d{4})?\b', str(addr))
                return match.group(1) if match else ""

            df["zip_code"] = df["address"].apply(extract_zip)
            df = df[df["zip_code"].str.startswith(zip_prefix)]

    if df.empty:
        return []

    # Group by community
    community_stats = df.groupby("louvain_community").agg({
        "fraud_risk_score": ["mean", "max", "count"],
        "is_excluded": "sum",
        "provider_type": lambda x: (x == "SNF").sum(),
    }).reset_index()

    community_stats.columns = [
        "community_id", "avg_risk_score", "max_risk_score",
        "member_count", "excluded_count", "snf_count"
    ]

    # Filter by min_size
    community_stats = community_stats[community_stats["member_count"] >= min_size]

    # Calculate HHA count and fraud density
    community_stats["hha_count"] = community_stats["member_count"] - community_stats["snf_count"]
    community_stats["fraud_density"] = community_stats["excluded_count"] / community_stats["member_count"]

    # Sort by avg risk score descending
    community_stats = community_stats.sort_values("avg_risk_score", ascending=False)

    # Get top N
    top_communities = community_stats.head(n)

    result = []
    for _, row in top_communities.iterrows():
        result.append({
            "community_id": int(row["community_id"]),
            "member_count": int(row["member_count"]),
            "avg_risk_score": float(row["avg_risk_score"]),
            "max_risk_score": float(row["max_risk_score"]),
            "excluded_count": int(row["excluded_count"]),
            "fraud_density": float(row["fraud_density"]),
            "snf_count": int(row["snf_count"]),
            "hha_count": int(row["hha_count"]),
        })

    return result
