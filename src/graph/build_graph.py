"""Build NetworkX heterogeneous graph from master files."""
import re
import pickle
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, Tuple

import networkx as nx
import pandas as pd

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"


def normalize_address(addr: str) -> str:
    """Normalize address for matching."""
    if not addr or pd.isna(addr):
        return ""
    addr = str(addr).upper().strip()

    # Standardize common abbreviations
    replacements = {
        ' STREET': ' ST', ' AVENUE': ' AVE', ' BOULEVARD': ' BLVD',
        ' DRIVE': ' DR', ' ROAD': ' RD', ' LANE': ' LN',
        ' COURT': ' CT', ' PLACE': ' PL', ' SUITE': ' STE',
        ' APARTMENT': ' APT', ' BUILDING': ' BLDG',
    }
    for old, new in replacements.items():
        addr = addr.replace(old, new)

    # Remove unit/suite numbers for broader matching
    addr = re.sub(r'\s+(STE|APT|UNIT|BLDG|FL|FLOOR|RM|ROOM)\s*#?\s*\S+', '', addr)
    addr = re.sub(r'\s+', ' ', addr).strip()

    return addr


def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only."""
    if not phone or pd.isna(phone):
        return ""
    # Keep only digits
    digits = re.sub(r'\D', '', str(phone))
    # Return last 10 digits (ignore country code)
    return digits[-10:] if len(digits) >= 10 else ""


def load_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load master facilities and ownership files."""
    print("=== Loading Master Files ===")

    facilities = pd.read_parquet(PROCESSED_DIR / "master_facilities.parquet")
    ownership = pd.read_parquet(PROCESSED_DIR / "master_ownership.parquet")

    print(f"  Facilities: {len(facilities):,} rows")
    print(f"  Ownership: {len(ownership):,} rows")

    return facilities, ownership


def build_graph(facilities: pd.DataFrame, ownership: pd.DataFrame) -> nx.Graph:
    """
    Build heterogeneous NetworkX graph.

    Nodes:
    - facility: one per row in master_facilities (keyed by NPI)
    - owner: one per unique normalized owner name
    - address: one per unique normalized address

    Edges:
    - OWNS: owner -> facility
    - MANAGED_BY: facility -> owner (where role = officer/manager)
    - SHARES_ADDRESS: facility <-> facility (same normalized address)
    - SHARES_PHONE: facility <-> facility (same phone number)
    """
    print("\n=== Building Graph ===")

    G = nx.Graph()

    # Track addresses and phones for facility-facility edges
    address_to_facilities: Dict[str, Set[str]] = defaultdict(set)
    phone_to_facilities: Dict[str, Set[str]] = defaultdict(set)

    # 1. Add facility nodes
    print("  Adding facility nodes...")
    facility_count = 0
    for _, row in facilities.iterrows():
        npi = str(row['npi'])
        if not npi or npi == 'nan':
            continue

        # Normalize address and phone
        norm_addr = normalize_address(row.get('address', ''))
        norm_phone = normalize_phone(row.get('phone', ''))

        # Add facility node with attributes
        G.add_node(
            f"facility:{npi}",
            node_type="facility",
            npi=npi,
            ccn=str(row.get('ccn', '')),
            name=str(row.get('facility_name', '')),
            address=str(row.get('address', '')),
            normalized_address=norm_addr,
            phone=str(row.get('phone', '')),
            normalized_phone=norm_phone,
            provider_type=str(row.get('provider_type', '')),
            is_excluded=bool(row.get('is_excluded', False)),
            exclusion_type=str(row.get('exclusion_type', '')),
            total_charges=float(row['total_charges']) if pd.notna(row.get('total_charges')) else 0.0,
            total_payments=float(row['total_payments']) if pd.notna(row.get('total_payments')) else 0.0,
            total_beneficiaries=float(row['total_beneficiaries']) if pd.notna(row.get('total_beneficiaries')) else 0.0,
        )
        facility_count += 1

        # Track for address/phone edges
        if norm_addr:
            address_to_facilities[norm_addr].add(npi)
        if norm_phone:
            phone_to_facilities[norm_phone].add(npi)

    print(f"    Added {facility_count:,} facility nodes")

    # 2. Add address nodes and facility-address edges
    print("  Adding address nodes...")
    address_count = 0
    for addr, fac_npis in address_to_facilities.items():
        if not addr or len(fac_npis) < 1:
            continue

        G.add_node(
            f"address:{addr}",
            node_type="address",
            address=addr,
            facility_count=len(fac_npis)
        )
        address_count += 1

        # Connect facilities to address
        for npi in fac_npis:
            G.add_edge(
                f"facility:{npi}",
                f"address:{addr}",
                edge_type="AT_ADDRESS"
            )

    print(f"    Added {address_count:,} address nodes")

    # 3. Add owner nodes and ownership edges
    print("  Adding owner nodes and edges...")
    owner_count = 0
    owns_edges = 0
    managed_by_edges = 0

    for _, row in ownership.iterrows():
        owner_name = str(row.get('owner_normalized_name', ''))
        facility_npi = str(row.get('facility_npi', ''))

        if not owner_name or not facility_npi or facility_npi == 'nan':
            continue

        # Add owner node if not exists
        owner_node = f"owner:{owner_name}"
        if owner_node not in G:
            G.add_node(
                owner_node,
                node_type="owner",
                name=owner_name,
                owner_type=str(row.get('owner_type', '')),
            )
            owner_count += 1

        facility_node = f"facility:{facility_npi}"
        if facility_node not in G:
            continue

        # Determine edge type based on role
        role = str(row.get('role', '')).upper()
        pct = row.get('pct_interest', '')

        # Parse percentage
        try:
            pct_float = float(str(pct).replace('%', '').strip()) if pct else 0.0
        except:
            pct_float = 0.0

        if 'OFFICER' in role or 'MANAGER' in role or 'DIRECTOR' in role:
            G.add_edge(
                facility_node,
                owner_node,
                edge_type="MANAGED_BY",
                role=role,
                pct_interest=pct_float
            )
            managed_by_edges += 1
        else:
            G.add_edge(
                owner_node,
                facility_node,
                edge_type="OWNS",
                role=role,
                pct_interest=pct_float
            )
            owns_edges += 1

    print(f"    Added {owner_count:,} owner nodes")
    print(f"    Added {owns_edges:,} OWNS edges")
    print(f"    Added {managed_by_edges:,} MANAGED_BY edges")

    # 4. Add SHARES_ADDRESS edges (facility-facility)
    print("  Adding SHARES_ADDRESS edges...")
    shares_address_edges = 0
    for addr, fac_npis in address_to_facilities.items():
        if len(fac_npis) > 1:
            fac_list = list(fac_npis)
            for i in range(len(fac_list)):
                for j in range(i + 1, len(fac_list)):
                    G.add_edge(
                        f"facility:{fac_list[i]}",
                        f"facility:{fac_list[j]}",
                        edge_type="SHARES_ADDRESS",
                        shared_address=addr
                    )
                    shares_address_edges += 1

    print(f"    Added {shares_address_edges:,} SHARES_ADDRESS edges")

    # 5. Add SHARES_PHONE edges (facility-facility)
    print("  Adding SHARES_PHONE edges...")
    shares_phone_edges = 0
    for phone, fac_npis in phone_to_facilities.items():
        if len(fac_npis) > 1:
            fac_list = list(fac_npis)
            for i in range(len(fac_list)):
                for j in range(i + 1, len(fac_list)):
                    # Check if edge already exists (from SHARES_ADDRESS)
                    node1 = f"facility:{fac_list[i]}"
                    node2 = f"facility:{fac_list[j]}"
                    if G.has_edge(node1, node2):
                        # Update existing edge
                        G[node1][node2]['shares_phone'] = True
                        G[node1][node2]['shared_phone'] = phone
                    else:
                        G.add_edge(
                            node1,
                            node2,
                            edge_type="SHARES_PHONE",
                            shared_phone=phone
                        )
                    shares_phone_edges += 1

    print(f"    Added {shares_phone_edges:,} SHARES_PHONE edges")

    return G


def print_graph_summary(G: nx.Graph):
    """Print summary statistics for the graph."""
    print("\n=== Graph Summary ===")

    # Count nodes by type
    node_types = defaultdict(int)
    for node, data in G.nodes(data=True):
        node_types[data.get('node_type', 'unknown')] += 1

    print("\nNodes by type:")
    for ntype, count in sorted(node_types.items()):
        print(f"  {ntype}: {count:,}")
    print(f"  TOTAL: {G.number_of_nodes():,}")

    # Count edges by type
    edge_types = defaultdict(int)
    for u, v, data in G.edges(data=True):
        edge_types[data.get('edge_type', 'unknown')] += 1

    print("\nEdges by type:")
    for etype, count in sorted(edge_types.items()):
        print(f"  {etype}: {count:,}")
    print(f"  TOTAL: {G.number_of_edges():,}")

    # Connected components
    components = list(nx.connected_components(G))
    print(f"\nConnected components: {len(components):,}")

    largest = max(components, key=len)
    print(f"Largest component size: {len(largest):,} nodes ({len(largest)/G.number_of_nodes()*100:.1f}%)")

    # Facility-specific stats
    facility_nodes = [n for n, d in G.nodes(data=True) if d.get('node_type') == 'facility']
    excluded_facilities = [n for n in facility_nodes if G.nodes[n].get('is_excluded', False)]
    print(f"\nFacility nodes: {len(facility_nodes):,}")
    print(f"Excluded facilities: {len(excluded_facilities):,}")


def save_graph(G: nx.Graph, output_path: Path):
    """Save graph to pickle file."""
    print(f"\n=== Saving Graph ===")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'wb') as f:
        pickle.dump(G, f)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Saved to {output_path} ({size_mb:.2f} MB)")


def build_and_save():
    """Main function to build and save the graph."""
    # Load data
    facilities, ownership = load_data()

    # Build graph
    G = build_graph(facilities, ownership)

    # Print summary
    print_graph_summary(G)

    # Save graph
    output_path = PROCESSED_DIR / "medigraph.gpickle"
    save_graph(G, output_path)

    return G


if __name__ == "__main__":
    build_and_save()
