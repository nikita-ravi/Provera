"""Ownership analysis tools."""
import pandas as pd
from pathlib import Path
from functools import lru_cache

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@lru_cache(maxsize=1)
def _load_ownership() -> pd.DataFrame:
    """Load ownership data (cached)."""
    return pd.read_parquet(PROCESSED_DIR / "master_ownership.parquet")


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

    if "facility_name_master" in features.columns:
        features["facility_name"] = features["facility_name_master"]
        features = features.drop(columns=["facility_name_master"])

    return features


@lru_cache(maxsize=1)
def _load_leie() -> pd.DataFrame:
    """Load LEIE exclusion list (cached)."""
    return pd.read_parquet(PROCESSED_DIR.parent / "filtered" / "leie_fl.parquet")


def normalize_name(name: str) -> str:
    """Normalize owner name for matching."""
    import re
    if not name or pd.isna(name):
        return ""
    name = str(name).upper().strip()
    # Remove common suffixes
    name = re.sub(r'\b(LLC|INC|CORP|LP|LLP|L\.L\.C\.|INCORPORATED|CO|COMPANY)\b', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = ' '.join(name.split())
    return name.strip()


def get_ownership_cluster(owner_name: str) -> dict:
    """
    Returns all facilities controlled by this owner (normalized name match).

    Output: {
        "owner_name": str,
        "owner_normalized": str,
        "facility_count": int,
        "facilities": list of {
            "npi": str,
            "facility_name": str,
            "role": str,
            "pct_interest": str or None,
            "fraud_risk_score": float,
            "is_excluded": bool,
        },
        "total_charges_across_cluster": float,
        "excluded_count": int,
    }
    """
    ownership = _load_ownership()
    features = _load_features()

    owner_normalized = normalize_name(owner_name)

    # Find all facilities owned by this person
    matches = ownership[ownership["owner_normalized_name"].apply(normalize_name) == owner_normalized]

    if matches.empty:
        # Try partial match
        matches = ownership[ownership["owner_normalized_name"].str.upper().str.contains(
            owner_normalized, na=False, regex=False
        )]

    if matches.empty:
        return {
            "owner_name": owner_name,
            "owner_normalized": owner_normalized,
            "facility_count": 0,
            "facilities": [],
            "total_charges_across_cluster": 0.0,
            "excluded_count": 0,
        }

    # Get unique facilities
    facility_npis = matches["facility_npi"].dropna().unique()

    facilities = []
    total_charges = 0.0
    excluded_count = 0

    for npi in facility_npis:
        npi_str = str(npi)
        facility_row = features[features["npi"].astype(str) == npi_str]

        if facility_row.empty:
            continue

        row = facility_row.iloc[0]

        # Get role and pct from ownership
        owner_row = matches[matches["facility_npi"].astype(str) == npi_str].iloc[0]

        facilities.append({
            "npi": npi_str,
            "facility_name": str(row.get("facility_name", "Unknown")) if pd.notna(row.get("facility_name")) else "Unknown",
            "role": str(owner_row.get("role", "Unknown")) if pd.notna(owner_row.get("role")) else "Unknown",
            "pct_interest": str(owner_row.get("pct_interest")) if pd.notna(owner_row.get("pct_interest")) else None,
            "fraud_risk_score": float(row["fraud_risk_score"]),
            "is_excluded": bool(row["is_excluded"]),
        })

        if pd.notna(row.get("total_charges")):
            total_charges += float(row["total_charges"])

        if row["is_excluded"]:
            excluded_count += 1

    # Sort by risk score
    facilities.sort(key=lambda x: x["fraud_risk_score"], reverse=True)

    return {
        "owner_name": owner_name,
        "owner_normalized": owner_normalized,
        "facility_count": len(facilities),
        "facilities": facilities,
        "total_charges_across_cluster": total_charges,
        "excluded_count": excluded_count,
    }


def get_facility_owners(npi: str) -> list:
    """
    Returns all owners/officers/managers of a facility.

    Output: list of {
        "owner_name": str,
        "owner_type": str,
        "role": str,
        "pct_interest": str or None,
        "other_facility_count": int,
        "is_excluded_owner": bool,
    }
    """
    ownership = _load_ownership()
    leie = _load_leie()

    npi_str = str(npi).strip()

    # Find ownership records for this facility
    facility_owners = ownership[ownership["facility_npi"].astype(str) == npi_str]

    if facility_owners.empty:
        return []

    # Get excluded individual names from LEIE
    excluded_names = set()
    if not leie.empty:
        for _, row in leie.iterrows():
            if pd.notna(row.get("LASTNAME")):
                name = f"{row.get('LASTNAME', '')}, {row.get('FIRSTNAME', '')}".upper().strip(", ")
                excluded_names.add(normalize_name(name))
            if pd.notna(row.get("BUSNAME")):
                excluded_names.add(normalize_name(row["BUSNAME"]))

    result = []
    for _, row in facility_owners.iterrows():
        owner_name = str(row.get("owner_name", "Unknown")) if pd.notna(row.get("owner_name")) else "Unknown"
        owner_normalized = normalize_name(owner_name)

        # Count other facilities owned by this person
        other_facilities = ownership[
            (ownership["owner_normalized_name"].apply(normalize_name) == owner_normalized) &
            (ownership["facility_npi"].astype(str) != npi_str)
        ]["facility_npi"].nunique()

        # Check if owner is excluded
        is_excluded = owner_normalized in excluded_names

        result.append({
            "owner_name": owner_name,
            "owner_type": str(row.get("owner_type", "Unknown")) if pd.notna(row.get("owner_type")) else "Unknown",
            "role": str(row.get("role", "Unknown")) if pd.notna(row.get("role")) else "Unknown",
            "pct_interest": str(row.get("pct_interest")) if pd.notna(row.get("pct_interest")) else None,
            "other_facility_count": int(other_facilities),
            "is_excluded_owner": is_excluded,
        })

    # Sort by other_facility_count descending (most connected owners first)
    result.sort(key=lambda x: x["other_facility_count"], reverse=True)

    return result


def get_shared_entities(community_id: int) -> dict:
    """
    Find shared owners, addresses, and phones within a community.

    Output: {
        "shared_owners": list of {"name": str, "facility_count": int},
        "shared_addresses": list of {"address": str, "facility_count": int, "npis": list},
        "shared_phones": list of {"phone": str, "facility_count": int, "npis": list},
    }
    """
    features = _load_features()
    ownership = _load_ownership()

    # Get community members
    members = features[features["louvain_community"] == community_id]
    member_npis = set(members["npi"].astype(str))

    # Find shared owners
    member_ownership = ownership[ownership["facility_npi"].astype(str).isin(member_npis)]

    owner_counts = member_ownership.groupby("owner_normalized_name")["facility_npi"].nunique()
    shared_owners = [
        {"name": name, "facility_count": int(count)}
        for name, count in owner_counts.items()
        if count > 1
    ]
    shared_owners.sort(key=lambda x: x["facility_count"], reverse=True)

    # Find shared addresses and phones from master
    master = pd.read_parquet(PROCESSED_DIR / "master_facilities.parquet")
    community_master = master[master["npi"].astype(str).isin(member_npis)]

    # Shared addresses
    address_groups = community_master.groupby("address")["npi"].apply(list)
    shared_addresses = [
        {"address": addr, "facility_count": len(npis), "npis": [str(n) for n in npis]}
        for addr, npis in address_groups.items()
        if len(npis) > 1 and pd.notna(addr) and addr.strip()
    ]
    shared_addresses.sort(key=lambda x: x["facility_count"], reverse=True)

    # Shared phones
    phone_groups = community_master.groupby("phone")["npi"].apply(list)
    shared_phones = [
        {"phone": phone, "facility_count": len(npis), "npis": [str(n) for n in npis]}
        for phone, npis in phone_groups.items()
        if len(npis) > 1 and pd.notna(phone) and phone.strip()
    ]
    shared_phones.sort(key=lambda x: x["facility_count"], reverse=True)

    return {
        "shared_owners": shared_owners,
        "shared_addresses": shared_addresses,
        "shared_phones": shared_phones,
    }
