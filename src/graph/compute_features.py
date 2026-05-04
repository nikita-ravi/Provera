"""Compute graph features for facility nodes."""
import pickle
from pathlib import Path
from collections import defaultdict

import networkx as nx
import pandas as pd
from community import community_louvain

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_graphs():
    """Load heterogeneous graph and facility projection."""
    print("=== Loading Graphs ===")

    with open(PROCESSED_DIR / "medigraph.gpickle", 'rb') as f:
        G = pickle.load(f)
    print(f"  Heterogeneous graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    with open(PROCESSED_DIR / "facility_graph.gpickle", 'rb') as f:
        F = pickle.load(f)
    print(f"  Facility graph: {F.number_of_nodes():,} nodes, {F.number_of_edges():,} edges")

    return G, F


def compute_centrality_features(F: nx.Graph) -> dict:
    """Compute centrality features on facility graph."""
    print("\n=== Computing Centrality Features ===")
    features = {}

    # PageRank
    print("  Computing PageRank...")
    pagerank = nx.pagerank(F, alpha=0.85)
    for node, pr in pagerank.items():
        features.setdefault(node, {})['pagerank'] = pr

    # Degree centrality
    print("  Computing degree centrality...")
    degree_cent = nx.degree_centrality(F)
    for node, dc in degree_cent.items():
        features.setdefault(node, {})['degree_centrality'] = dc

    # Clustering coefficient
    print("  Computing clustering coefficient...")
    clustering = nx.clustering(F)
    for node, cc in clustering.items():
        features.setdefault(node, {})['clustering_coeff'] = cc

    # Betweenness centrality (sampled for speed)
    print("  Computing betweenness centrality (k=500 sample)...")
    k = min(500, F.number_of_nodes())
    betweenness = nx.betweenness_centrality(F, k=k)
    for node, bc in betweenness.items():
        features.setdefault(node, {})['betweenness_centrality'] = bc

    # Degree (raw count)
    for node in F.nodes():
        features.setdefault(node, {})['degree'] = F.degree(node)

    return features


def compute_louvain_communities(F: nx.Graph) -> dict:
    """Compute Louvain communities and derived features."""
    print("\n=== Computing Louvain Communities ===")

    # Run Louvain
    partition = community_louvain.best_partition(F, random_state=42)

    # Count community sizes
    community_sizes = defaultdict(int)
    for node, comm in partition.items():
        community_sizes[comm] += 1

    print(f"  Found {len(community_sizes):,} communities")
    print(f"  Largest community: {max(community_sizes.values()):,} nodes")
    print(f"  Smallest community: {min(community_sizes.values()):,} nodes")

    # Count excluded facilities per community
    community_excluded = defaultdict(int)
    for node, comm in partition.items():
        if F.nodes[node].get('is_excluded', False):
            community_excluded[comm] += 1

    # Compute features
    features = {}
    for node, comm in partition.items():
        size = community_sizes[comm]
        excluded_count = community_excluded[comm]
        fraud_density = excluded_count / size if size > 0 else 0.0

        features[node] = {
            'louvain_community': comm,
            'community_size': size,
            'community_excluded_count': excluded_count,
            'community_fraud_density': fraud_density,
        }

    # Print top communities by fraud density
    print("\n  Top 10 communities by fraud density:")
    comm_fraud = [(c, community_excluded[c] / community_sizes[c], community_sizes[c], community_excluded[c])
                  for c in community_sizes if community_sizes[c] >= 5]
    comm_fraud.sort(key=lambda x: x[1], reverse=True)
    for comm, density, size, excluded in comm_fraud[:10]:
        print(f"    Community {comm}: {density*100:.1f}% fraud ({excluded}/{size} facilities)")

    return features


def compute_neighbor_features(G: nx.Graph, F: nx.Graph) -> dict:
    """Compute neighbor-based features."""
    print("\n=== Computing Neighbor Features ===")
    features = {}

    # Get facility nodes
    facility_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'facility']

    for node in facility_nodes:
        # Fraud neighbor ratio in facility graph
        neighbors = list(F.neighbors(node)) if node in F else []
        if neighbors:
            excluded_neighbors = sum(1 for n in neighbors if F.nodes[n].get('is_excluded', False))
            fraud_neighbor_ratio = excluded_neighbors / len(neighbors)
        else:
            fraud_neighbor_ratio = 0.0

        features[node] = {
            'fraud_neighbor_ratio': fraud_neighbor_ratio,
            'neighbor_count': len(neighbors),
        }

    return features


def compute_ownership_features(G: nx.Graph) -> dict:
    """Compute ownership-related features."""
    print("\n=== Computing Ownership Features ===")
    features = {}

    # Get facility and owner nodes
    facility_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'facility']
    owner_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'owner']

    # Count facilities per owner
    owner_facility_counts = {}
    for owner in owner_nodes:
        facilities = [n for n in G.neighbors(owner) if G.nodes[n].get('node_type') == 'facility']
        owner_facility_counts[owner] = len(facilities)

    # For each facility, find max owner facility count
    for node in facility_nodes:
        # Get connected owners
        owners = [n for n in G.neighbors(node) if G.nodes[n].get('node_type') == 'owner']

        if owners:
            max_owner_facilities = max(owner_facility_counts.get(o, 0) for o in owners)
            total_owner_facilities = sum(owner_facility_counts.get(o, 0) for o in owners)
            owner_count = len(owners)
        else:
            max_owner_facilities = 0
            total_owner_facilities = 0
            owner_count = 0

        features[node] = {
            'owner_count': owner_count,
            'max_owner_facility_count': max_owner_facilities,
            'total_owner_facility_count': total_owner_facilities,
        }

    return features


def compute_sharing_features(G: nx.Graph) -> dict:
    """Compute address/phone sharing features."""
    print("\n=== Computing Sharing Features ===")
    features = {}

    # Get facility nodes
    facility_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'facility']

    for node in facility_nodes:
        # Count shared address/phone
        shared_address_count = 0
        shared_phone_count = 0

        for neighbor in G.neighbors(node):
            if G.nodes[neighbor].get('node_type') == 'facility':
                edge_data = G.get_edge_data(node, neighbor, {})
                if edge_data.get('edge_type') == 'SHARES_ADDRESS':
                    shared_address_count += 1
                if edge_data.get('edge_type') == 'SHARES_PHONE' or edge_data.get('shares_phone'):
                    shared_phone_count += 1
            elif G.nodes[neighbor].get('node_type') == 'address':
                # Count facilities at same address
                address_facilities = [n for n in G.neighbors(neighbor)
                                     if G.nodes[n].get('node_type') == 'facility' and n != node]
                shared_address_count = len(address_facilities)

        features[node] = {
            'shared_address_count': shared_address_count,
            'shared_phone_count': shared_phone_count,
        }

    return features


def merge_features(*feature_dicts) -> dict:
    """Merge multiple feature dictionaries."""
    merged = defaultdict(dict)
    for fd in feature_dicts:
        for node, feats in fd.items():
            merged[node].update(feats)
    return dict(merged)


def features_to_dataframe(features: dict, G: nx.Graph) -> pd.DataFrame:
    """Convert features dict to DataFrame with NPI as index."""
    print("\n=== Converting to DataFrame ===")

    rows = []
    for node, feats in features.items():
        if not node.startswith('facility:'):
            continue

        npi = node.replace('facility:', '')
        row = {'npi': npi}
        row.update(feats)

        # Add node attributes
        node_data = G.nodes.get(node, {})
        row['is_excluded'] = node_data.get('is_excluded', False)
        row['provider_type'] = node_data.get('provider_type', '')
        row['total_charges'] = node_data.get('total_charges', 0.0)
        row['total_payments'] = node_data.get('total_payments', 0.0)
        row['total_beneficiaries'] = node_data.get('total_beneficiaries', 0.0)

        rows.append(row)

    df = pd.DataFrame(rows)

    # Compute derived billing features
    df['charges_per_beneficiary'] = df['total_charges'] / df['total_beneficiaries'].replace(0, 1)
    df['payment_to_charge_ratio'] = df['total_payments'] / df['total_charges'].replace(0, 1)
    df['avg_payment_per_beneficiary'] = df['total_payments'] / df['total_beneficiaries'].replace(0, 1)

    # Fill NaN with 0
    df = df.fillna(0)

    print(f"  Feature matrix: {len(df):,} facilities x {len(df.columns)} features")
    print(f"  Excluded facilities: {df['is_excluded'].sum():,}")

    return df


def save_features(df: pd.DataFrame, output_path: Path):
    """Save feature DataFrame to parquet."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Saved to {output_path} ({size_mb:.2f} MB)")


def compute_all_features():
    """Main function to compute all features."""
    # Load graphs
    G, F = load_graphs()

    # Compute feature groups
    centrality_feats = compute_centrality_features(F)
    louvain_feats = compute_louvain_communities(F)
    neighbor_feats = compute_neighbor_features(G, F)
    ownership_feats = compute_ownership_features(G)
    sharing_feats = compute_sharing_features(G)

    # Merge all features
    all_features = merge_features(
        centrality_feats,
        louvain_feats,
        neighbor_feats,
        ownership_feats,
        sharing_feats
    )

    # Convert to DataFrame
    df = features_to_dataframe(all_features, G)

    # Save
    save_features(df, PROCESSED_DIR / "facility_features.parquet")

    return df


if __name__ == "__main__":
    compute_all_features()
