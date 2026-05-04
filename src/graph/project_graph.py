"""Project heterogeneous graph to facility-only graph for community detection."""
import pickle
from pathlib import Path
from collections import defaultdict

import networkx as nx

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_graph() -> nx.Graph:
    """Load the heterogeneous graph."""
    graph_path = PROCESSED_DIR / "medigraph.gpickle"
    with open(graph_path, 'rb') as f:
        return pickle.load(f)


def project_to_facility_graph(G: nx.Graph) -> nx.Graph:
    """
    Project heterogeneous graph to facility-only graph.

    Two facilities are connected if they:
    1. Share an owner (connected via same owner node)
    2. Share an address (SHARES_ADDRESS edge)
    3. Share a phone (SHARES_PHONE edge)

    Edge weights represent the number of shared connections.
    """
    print("=== Projecting to Facility Graph ===")

    # Get facility nodes
    facility_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'facility']
    print(f"  Facility nodes: {len(facility_nodes):,}")

    # Create facility-only graph
    F = nx.Graph()

    # Add all facility nodes with their attributes
    for node in facility_nodes:
        F.add_node(node, **G.nodes[node])

    # Track edge sources for weighting
    edge_weights = defaultdict(lambda: {'weight': 0, 'shared_owners': 0, 'shared_addresses': 0, 'shared_phones': 0})

    # 1. Find facilities sharing owners (via bipartite projection)
    print("  Finding shared owners...")
    owner_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'owner']

    for owner in owner_nodes:
        # Get all facilities connected to this owner
        connected_facilities = [
            n for n in G.neighbors(owner)
            if G.nodes[n].get('node_type') == 'facility'
        ]

        # Create edges between all pairs
        for i in range(len(connected_facilities)):
            for j in range(i + 1, len(connected_facilities)):
                f1, f2 = connected_facilities[i], connected_facilities[j]
                key = tuple(sorted([f1, f2]))
                edge_weights[key]['weight'] += 1
                edge_weights[key]['shared_owners'] += 1

    # 2. Find direct facility-facility edges (SHARES_ADDRESS, SHARES_PHONE)
    print("  Finding shared addresses and phones...")
    for u, v, data in G.edges(data=True):
        if G.nodes[u].get('node_type') == 'facility' and G.nodes[v].get('node_type') == 'facility':
            key = tuple(sorted([u, v]))
            edge_type = data.get('edge_type', '')

            if edge_type == 'SHARES_ADDRESS' or data.get('shares_phone'):
                edge_weights[key]['weight'] += 1

            if edge_type == 'SHARES_ADDRESS':
                edge_weights[key]['shared_addresses'] += 1

            if edge_type == 'SHARES_PHONE' or data.get('shares_phone'):
                edge_weights[key]['shared_phones'] += 1

    # Add edges to facility graph
    for (f1, f2), attrs in edge_weights.items():
        F.add_edge(f1, f2, **attrs)

    print(f"  Facility graph nodes: {F.number_of_nodes():,}")
    print(f"  Facility graph edges: {F.number_of_edges():,}")

    # Connected components in facility graph
    components = list(nx.connected_components(F))
    print(f"  Connected components: {len(components):,}")

    if components:
        largest = max(components, key=len)
        print(f"  Largest component: {len(largest):,} nodes")

    return F


def save_facility_graph(F: nx.Graph, output_path: Path):
    """Save facility projection graph."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        pickle.dump(F, f)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Saved to {output_path} ({size_mb:.2f} MB)")


def project_and_save():
    """Main function to project and save facility graph."""
    G = load_graph()
    F = project_to_facility_graph(G)
    save_facility_graph(F, PROCESSED_DIR / "facility_graph.gpickle")
    return F


if __name__ == "__main__":
    project_and_save()
