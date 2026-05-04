"""Red flag checklist tools."""
import pandas as pd
from pathlib import Path
from functools import lru_cache
from collections import Counter

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@lru_cache(maxsize=1)
def _load_features() -> pd.DataFrame:
    """Load facility features (cached)."""
    return pd.read_parquet(PROCESSED_DIR / "facility_features.parquet")


@lru_cache(maxsize=1)
def _load_ownership() -> pd.DataFrame:
    """Load ownership data (cached)."""
    return pd.read_parquet(PROCESSED_DIR / "master_ownership.parquet")


@lru_cache(maxsize=1)
def _load_master() -> pd.DataFrame:
    """Load master facilities (cached)."""
    return pd.read_parquet(PROCESSED_DIR / "master_facilities.parquet")


def check_ego_red_flags(member_npis: set, seed_npi: str = None) -> dict:
    """
    Runs the 5-point red flag checklist against an ego network cluster.

    Same red flags as check_red_flags but operates on a set of NPIs
    instead of a Louvain community ID.

    Args:
        member_npis: Set of NPI strings in the ego network
        seed_npi: Optional seed NPI for labeling

    Output: Same structure as check_red_flags but with "ego_network" label
    """
    features = _load_features()
    ownership = _load_ownership()
    master = _load_master()

    # Get members from features
    members = features[features["npi"].astype(str).isin(member_npis)]

    if members.empty:
        return {"error": "No valid NPIs found in ego network"}

    member_count = len(member_npis)

    details = {}
    flags_triggered = 0

    # === FLAG 1: Ownership concentration ===
    member_ownership = ownership[ownership["facility_npi"].astype(str).isin(member_npis)]
    owner_counts = member_ownership.groupby("owner_normalized_name")["facility_npi"].nunique()
    concentrated_owners = owner_counts[owner_counts >= 3]

    if len(concentrated_owners) > 0:
        top_owner = concentrated_owners.idxmax()
        top_count = int(concentrated_owners.max())
        details["ownership_concentration"] = {
            "triggered": True,
            "detail": f"{top_owner} controls {top_count}/{member_count} facilities"
        }
        flags_triggered += 1
    else:
        max_owner = owner_counts.idxmax() if len(owner_counts) > 0 else "None"
        max_count = int(owner_counts.max()) if len(owner_counts) > 0 else 0
        details["ownership_concentration"] = {
            "triggered": False,
            "detail": f"Max ownership: {max_owner} with {max_count} facilities (threshold: 3)"
        }

    # === FLAG 2: Shared address ===
    community_master = master[master["npi"].astype(str).isin(member_npis)]
    address_groups = community_master.groupby("address").agg({
        "npi": "count",
        "facility_name": list
    })
    address_groups = address_groups[address_groups["npi"] >= 2]

    shared_address_found = False
    shared_address_detail = ""

    for addr, row in address_groups.iterrows():
        if pd.isna(addr) or not str(addr).strip():
            continue
        names = row["facility_name"]
        unique_names = len(set(str(n).upper() for n in names if pd.notna(n)))
        if unique_names >= 2:
            shared_address_found = True
            shared_address_detail = f"{row['npi']} facilities at {addr}"
            break

    details["shared_address"] = {
        "triggered": shared_address_found,
        "detail": shared_address_detail if shared_address_found else "No shared addresses with different entity names"
    }
    if shared_address_found:
        flags_triggered += 1

    # === FLAG 3: LEIE connection ===
    excluded_members = members[members["is_excluded"] == True]
    excluded_count = len(excluded_members)

    if excluded_count > 0:
        excluded_names = excluded_members["npi"].tolist()
        excluded_details = community_master[community_master["npi"].astype(str).isin([str(n) for n in excluded_names])]
        if not excluded_details.empty:
            first_excluded = excluded_details.iloc[0]
            excl_name = first_excluded.get("facility_name", "Unknown")
            excl_type = first_excluded.get("exclusion_type", "Unknown")
            details["leie_connection"] = {
                "triggered": True,
                "detail": f"{excl_name} excluded ({excl_type})"
            }
        else:
            details["leie_connection"] = {
                "triggered": True,
                "detail": f"{excluded_count} excluded facilities in cluster"
            }
        flags_triggered += 1
    else:
        details["leie_connection"] = {
            "triggered": False,
            "detail": "No LEIE-excluded facilities or owners"
        }

    # === FLAG 4: Billing deviation ===
    all_features = features[features["avg_payment_per_beneficiary"] > 0]
    if len(all_features) > 0:
        state_median = all_features["avg_payment_per_beneficiary"].median()
        state_std = all_features["avg_payment_per_beneficiary"].std()

        members_with_billing = members[members["avg_payment_per_beneficiary"] > 0]
        high_billing = members_with_billing[
            members_with_billing["avg_payment_per_beneficiary"] > (state_median + 2 * state_std)
        ]

        if len(high_billing) > 0:
            worst = high_billing.iloc[0]
            facility_avg = worst["avg_payment_per_beneficiary"]
            sigma = (facility_avg - state_median) / state_std
            details["billing_deviation"] = {
                "triggered": True,
                "detail": f"Avg ${facility_avg:,.0f}/bene vs state median ${state_median:,.0f} ({sigma:.1f}σ)"
            }
            flags_triggered += 1
        else:
            details["billing_deviation"] = {
                "triggered": False,
                "detail": f"All facilities within 2σ of state median (${state_median:,.0f})"
            }
    else:
        details["billing_deviation"] = {
            "triggered": False,
            "detail": "No billing data available for comparison"
        }

    # === FLAG 5: Shared phone ===
    phone_groups = community_master.groupby("phone").agg({
        "npi": "count",
        "facility_name": list
    })
    phone_groups = phone_groups[phone_groups["npi"] >= 2]

    shared_phone_found = False
    shared_phone_detail = ""

    for phone, row in phone_groups.iterrows():
        if pd.isna(phone) or not str(phone).strip():
            continue
        names = row["facility_name"]
        unique_names = len(set(str(n).upper() for n in names if pd.notna(n)))
        if unique_names >= 2:
            shared_phone_found = True
            shared_phone_detail = f"{row['npi']} facilities share {phone}"
            break

    details["shared_phone"] = {
        "triggered": shared_phone_found,
        "detail": shared_phone_detail if shared_phone_found else "No shared phones with different entity names"
    }
    if shared_phone_found:
        flags_triggered += 1

    # Compute legitimacy signals
    legitimacy = _compute_legitimacy_signals(members)

    # Calculate fraud density (percentage of excluded facilities)
    fraud_density = excluded_count / member_count if member_count > 0 else 0

    # Determine risk label with legitimacy modifiers
    # HIGH FRAUD DENSITY OVERRIDE: If >= 50% of facilities are LEIE excluded,
    # this is strong evidence of actual fraud - classify as HIGH regardless
    if fraud_density >= 0.5:
        risk_label = "HIGH"
        classification_note = f"Classified HIGH due to {fraud_density:.0%} LEIE exclusion rate ({excluded_count}/{member_count} facilities)"
    elif flags_triggered >= 3:
        if legitimacy["should_downgrade"]:
            risk_label = "MEDIUM"
            classification_note = "Downgraded from HIGH due to legitimacy signals"
        else:
            risk_label = "HIGH"
            classification_note = None
    elif flags_triggered >= 1:
        risk_label = "MEDIUM"
        classification_note = None
    else:
        risk_label = "LOW"
        classification_note = None

    result = {
        "cluster_type": "ego_network",
        "seed_npi": seed_npi,
        "member_count": member_count,
        "flags_triggered": flags_triggered,
        "total_flags": 5,
        "fraud_density": round(fraud_density, 2),
        "excluded_count": excluded_count,
        "details": details,
        "risk_label": risk_label,
        "legitimacy_signals": legitimacy,
    }

    if classification_note:
        result["classification_note"] = classification_note

    return result


def _detect_false_positive_patterns(members: pd.DataFrame, master: pd.DataFrame) -> list:
    """
    Detect patterns that suggest a cluster may be a false positive.

    Returns a list of warning strings to include in the investigation.
    """
    warnings = []

    # Get facility names from master
    member_npis = set(members["npi"].astype(str))
    member_master = master[master["npi"].astype(str).isin(member_npis)]

    # Pattern 1: Names suggesting legitimate nonprofits
    nonprofit_keywords = [
        "UNITED WAY", "CATHOLIC", "JEWISH", "LUTHERAN", "METHODIST",
        "BAPTIST", "PRESBYTERIAN", "SALVATION ARMY", "RED CROSS",
        "HOSPICE", "VISITING NURSE", "VNA", "COMMUNITY HEALTH",
        "UNIVERSITY", "HOSPITAL", "MEDICAL CENTER"
    ]

    for _, row in member_master.iterrows():
        name = str(row.get("facility_name", "")).upper()
        for keyword in nonprofit_keywords:
            if keyword in name:
                warnings.append(
                    f"POTENTIAL FALSE POSITIVE: '{row['facility_name']}' contains '{keyword}' "
                    f"suggesting legitimate nonprofit/institutional affiliation. "
                    f"Verify 501(c)(3) status via IRS or GuideStar before escalating."
                )
                break

    # Pattern 1b: PE-backed healthcare chains (often trigger ownership flags legitimately)
    pe_keywords = [
        "NAUTIC", "BLACKSTONE", "KKR", "CARLYLE", "APOLLO", "WARBURG",
        "BAIN CAPITAL", "TPG", "ADVENT", "WELSH CARSON", "HELLMAN",
        "PLATINUM EQUITY", "KINDRED", "AMEDISYS", "BROOKDALE", "GENESIS"
    ]

    # Check ownership data for PE patterns
    ownership = _load_ownership()
    member_ownership = ownership[ownership["facility_npi"].astype(str).isin(member_npis)]

    for _, row in member_ownership.iterrows():
        owner_name = str(row.get("owner_normalized_name", "")).upper()
        for keyword in pe_keywords:
            if keyword in owner_name:
                warnings.append(
                    f"POTENTIAL FALSE POSITIVE: Ownership by '{row.get('owner_normalized_name', 'Unknown')}' "
                    f"suggests institutional/PE investor backing. PE-backed healthcare chains "
                    f"often trigger red flags due to multi-facility ownership but are legitimate operations. "
                    f"Verify corporate structure before escalating."
                )
                break

    # Pattern 2: Very old entities (>30 years)
    if "entity_age_years" in members.columns:
        old_entities = members[members["entity_age_years"] > 30]
        if len(old_entities) > 0:
            max_age = members["entity_age_years"].max()
            warnings.append(
                f"POTENTIAL FALSE POSITIVE: Cluster contains entity operating for {max_age:.0f} years. "
                f"Long-established organizations rarely become fraud rings. "
                f"Verify this is not a legitimate healthcare system before escalating."
            )

    # Pattern 3: Known healthcare system names
    system_keywords = [
        "HCA", "KINDRED", "AMEDISYS", "BROOKDALE", "GENESIS", "ENCOMPASS",
        "BAYCARE", "ADVENTHEALTH", "BAPTIST HEALTH", "CLEVELAND CLINIC",
        "MAYO", "JOHNS HOPKINS"
    ]

    for _, row in member_master.iterrows():
        name = str(row.get("facility_name", "")).upper()
        for keyword in system_keywords:
            if keyword in name:
                warnings.append(
                    f"POTENTIAL FALSE POSITIVE: '{row['facility_name']}' appears affiliated with "
                    f"major healthcare system '{keyword}'. Corporate subsidiaries often trigger "
                    f"red flags due to shared infrastructure. Verify independence before escalating."
                )
                break

    # Pattern 4: NPPES_LINKED exclusions (data quality issue)
    if "exclusion_type" in members.columns:
        nppes_linked = members[members["exclusion_type"] == "NPPES_LINKED"]
        if len(nppes_linked) > 0:
            warnings.append(
                f"DATA QUALITY WARNING: {len(nppes_linked)} facility(ies) show 'NPPES_LINKED' "
                f"exclusion type. This may indicate data linkage issues rather than actual "
                f"LEIE exclusions. Verify exclusion status directly with OIG LEIE database."
            )

    # Deduplicate warnings
    return list(set(warnings))


def _compute_legitimacy_signals(members: pd.DataFrame) -> dict:
    """
    Compute legitimacy signals that can mitigate red flag classifications.

    These signals indicate established, legitimate operations that may
    trigger red flags for benign reasons (e.g., large nonprofit networks).

    Returns:
        dict with legitimacy indicators and whether to downgrade classification
    """
    signals = {
        "has_nonprofit": False,
        "has_established_entity": False,  # >10 years old
        "has_quality_ratings": False,
        "has_staffing_data": False,
        "nonprofit_count": 0,
        "avg_entity_age_years": 0.0,
        "quality_rated_count": 0,
        "mitigating_factors": [],
        "should_downgrade": False,
    }

    # Check for nonprofits
    if "is_nonprofit" in members.columns:
        nonprofit_count = members["is_nonprofit"].sum()
        signals["nonprofit_count"] = int(nonprofit_count)
        if nonprofit_count > 0:
            signals["has_nonprofit"] = True
            signals["mitigating_factors"].append(
                f"{nonprofit_count} nonprofit organization(s) in community"
            )

    # Check entity age
    if "entity_age_years" in members.columns:
        avg_age = members["entity_age_years"].mean()
        max_age = members["entity_age_years"].max()
        signals["avg_entity_age_years"] = round(float(avg_age), 1) if pd.notna(avg_age) else 0.0
        if max_age > 10:
            signals["has_established_entity"] = True
            signals["mitigating_factors"].append(
                f"Established entity (oldest: {max_age:.0f} years)"
            )

    # Check quality ratings
    if "has_quality_data" in members.columns:
        quality_count = members["has_quality_data"].sum()
        signals["quality_rated_count"] = int(quality_count)
        if quality_count > 0:
            signals["has_quality_ratings"] = True
            signals["mitigating_factors"].append(
                f"{quality_count} facility(ies) with CMS quality ratings"
            )

    # Check star ratings
    if "has_star_rating" in members.columns:
        star_count = members["has_star_rating"].sum()
        if star_count > 0:
            signals["mitigating_factors"].append(
                f"{star_count} facility(ies) with CMS star ratings"
            )

    # Determine if classification should be downgraded
    # Downgrade HIGH → MEDIUM if:
    # - Has nonprofit AND established entity (>10 years), OR
    # - Has quality ratings AND established entity, OR
    # - Majority are nonprofits
    legitimacy_score = sum([
        signals["has_nonprofit"],
        signals["has_established_entity"],
        signals["has_quality_ratings"],
    ])

    member_count = len(members)
    nonprofit_majority = signals["nonprofit_count"] > (member_count / 2)

    if legitimacy_score >= 2 or nonprofit_majority:
        signals["should_downgrade"] = True

    return signals


def check_red_flags(community_id: int) -> dict:
    """
    Runs the 5-point red flag checklist against a community.

    Red Flags:
    1. Ownership concentration: 1 person/entity controls >=3 facilities
    2. Shared address: >=2 facilities at same normalized address with different names
    3. LEIE connection: >=1 facility or owner is LEIE-excluded
    4. Billing deviation: >=1 facility charges >2σ above FL state median per beneficiary
    5. Shared phone: >=2 facilities share a phone number with different names

    Legitimacy modifiers can downgrade HIGH → MEDIUM when strong signals present:
    - Nonprofit status
    - Established entities (>10 years old)
    - CMS quality/star ratings

    Output: {
        "community_id": int,
        "flags_triggered": int,
        "total_flags": 5,
        "details": {
            "ownership_concentration": {"triggered": bool, "detail": str},
            "shared_address": {"triggered": bool, "detail": str},
            "leie_connection": {"triggered": bool, "detail": str},
            "billing_deviation": {"triggered": bool, "detail": str},
            "shared_phone": {"triggered": bool, "detail": str},
        },
        "risk_label": "HIGH" or "MEDIUM" or "LOW",
    }
    """
    features = _load_features()
    ownership = _load_ownership()
    master = _load_master()

    # Get community members
    members = features[features["louvain_community"] == community_id]

    if members.empty:
        return {"error": f"Community {community_id} not found"}

    member_npis = set(members["npi"].astype(str))
    member_count = len(member_npis)

    details = {}
    flags_triggered = 0

    # === FLAG 1: Ownership concentration ===
    member_ownership = ownership[ownership["facility_npi"].astype(str).isin(member_npis)]
    owner_counts = member_ownership.groupby("owner_normalized_name")["facility_npi"].nunique()
    concentrated_owners = owner_counts[owner_counts >= 3]

    if len(concentrated_owners) > 0:
        top_owner = concentrated_owners.idxmax()
        top_count = int(concentrated_owners.max())
        details["ownership_concentration"] = {
            "triggered": True,
            "detail": f"{top_owner} controls {top_count}/{member_count} facilities"
        }
        flags_triggered += 1
    else:
        max_owner = owner_counts.idxmax() if len(owner_counts) > 0 else "None"
        max_count = int(owner_counts.max()) if len(owner_counts) > 0 else 0
        details["ownership_concentration"] = {
            "triggered": False,
            "detail": f"Max ownership: {max_owner} with {max_count} facilities (threshold: 3)"
        }

    # === FLAG 2: Shared address ===
    community_master = master[master["npi"].astype(str).isin(member_npis)]
    address_groups = community_master.groupby("address").agg({
        "npi": "count",
        "facility_name": list
    })
    address_groups = address_groups[address_groups["npi"] >= 2]

    # Filter to addresses where facilities have different names
    shared_address_found = False
    shared_address_detail = ""

    for addr, row in address_groups.iterrows():
        if pd.isna(addr) or not str(addr).strip():
            continue
        names = row["facility_name"]
        unique_names = len(set(str(n).upper() for n in names if pd.notna(n)))
        if unique_names >= 2:
            shared_address_found = True
            shared_address_detail = f"{row['npi']} facilities at {addr}"
            break

    details["shared_address"] = {
        "triggered": shared_address_found,
        "detail": shared_address_detail if shared_address_found else "No shared addresses with different entity names"
    }
    if shared_address_found:
        flags_triggered += 1

    # === FLAG 3: LEIE connection ===
    excluded_members = members[members["is_excluded"] == True]
    excluded_count = len(excluded_members)

    if excluded_count > 0:
        excluded_names = excluded_members["npi"].tolist()
        # Get exclusion details from master
        excluded_details = community_master[community_master["npi"].astype(str).isin([str(n) for n in excluded_names])]
        if not excluded_details.empty:
            first_excluded = excluded_details.iloc[0]
            excl_name = first_excluded.get("facility_name", "Unknown")
            excl_type = first_excluded.get("exclusion_type", "Unknown")
            details["leie_connection"] = {
                "triggered": True,
                "detail": f"{excl_name} excluded ({excl_type})"
            }
        else:
            details["leie_connection"] = {
                "triggered": True,
                "detail": f"{excluded_count} excluded facilities in community"
            }
        flags_triggered += 1
    else:
        details["leie_connection"] = {
            "triggered": False,
            "detail": "No LEIE-excluded facilities or owners"
        }

    # === FLAG 4: Billing deviation ===
    # Calculate state statistics for facilities with billing data
    all_features = features[features["avg_payment_per_beneficiary"] > 0]
    if len(all_features) > 0:
        state_median = all_features["avg_payment_per_beneficiary"].median()
        state_std = all_features["avg_payment_per_beneficiary"].std()

        # Check community members
        members_with_billing = members[members["avg_payment_per_beneficiary"] > 0]
        high_billing = members_with_billing[
            members_with_billing["avg_payment_per_beneficiary"] > (state_median + 2 * state_std)
        ]

        if len(high_billing) > 0:
            worst = high_billing.iloc[0]
            facility_avg = worst["avg_payment_per_beneficiary"]
            sigma = (facility_avg - state_median) / state_std
            details["billing_deviation"] = {
                "triggered": True,
                "detail": f"Avg ${facility_avg:,.0f}/bene vs state median ${state_median:,.0f} ({sigma:.1f}σ)"
            }
            flags_triggered += 1
        else:
            details["billing_deviation"] = {
                "triggered": False,
                "detail": f"All facilities within 2σ of state median (${state_median:,.0f})"
            }
    else:
        details["billing_deviation"] = {
            "triggered": False,
            "detail": "No billing data available for comparison"
        }

    # === FLAG 5: Shared phone ===
    phone_groups = community_master.groupby("phone").agg({
        "npi": "count",
        "facility_name": list
    })
    phone_groups = phone_groups[phone_groups["npi"] >= 2]

    shared_phone_found = False
    shared_phone_detail = ""

    for phone, row in phone_groups.iterrows():
        if pd.isna(phone) or not str(phone).strip():
            continue
        names = row["facility_name"]
        unique_names = len(set(str(n).upper() for n in names if pd.notna(n)))
        if unique_names >= 2:
            shared_phone_found = True
            shared_phone_detail = f"{row['npi']} facilities share {phone}"
            break

    details["shared_phone"] = {
        "triggered": shared_phone_found,
        "detail": shared_phone_detail if shared_phone_found else "No shared phones with different entity names"
    }
    if shared_phone_found:
        flags_triggered += 1

    # Compute legitimacy signals
    legitimacy = _compute_legitimacy_signals(members)

    # Detect potential false positive patterns
    false_positive_warnings = _detect_false_positive_patterns(members, master)

    # Calculate fraud density (percentage of excluded facilities)
    fraud_density = excluded_count / member_count if member_count > 0 else 0

    # Check if exclusions are direct LEIE or linked (data quality issue)
    # OWNER_LINKED and NPPES_LINKED are less reliable than direct exclusions
    linked_exclusion_types = {"OWNER_LINKED", "NPPES_LINKED"}
    # Get exclusion_type from master (not features)
    excluded_master = community_master[community_master["npi"].astype(str).isin(
        [str(n) for n in members[members["is_excluded"] == True]["npi"].tolist()]
    )]
    if "exclusion_type" in excluded_master.columns:
        exclusion_types = set(excluded_master["exclusion_type"].dropna().unique())
    else:
        exclusion_types = set()
    has_only_linked_exclusions = len(exclusion_types) > 0 and exclusion_types.issubset(linked_exclusion_types)

    # Determine risk label with legitimacy modifiers
    # Also downgrade if strong false positive patterns detected
    has_strong_fp_warning = any(
        "POTENTIAL FALSE POSITIVE" in w and (
            "years" in w or
            "nonprofit" in w.lower() or
            "pe investor" in w.lower() or
            "institutional" in w.lower()
        )
        for w in false_positive_warnings
    )

    # Check for very old entities (>30 years) which are unlikely to be fraud rings
    has_very_old_entity = False
    if "entity_age_years" in members.columns:
        max_age = members["entity_age_years"].max()
        if pd.notna(max_age) and max_age > 30:
            has_very_old_entity = True

    # HIGH FRAUD DENSITY OVERRIDE: If >= 50% of facilities are LEIE excluded,
    # this is strong evidence of actual fraud - classify as HIGH regardless
    # EXCEPTION: Don't override if exclusions are only LINKED types AND entity is very old
    if fraud_density >= 0.5 and not (has_only_linked_exclusions and has_very_old_entity):
        risk_label = "HIGH"
        classification_note = f"Classified HIGH due to {fraud_density:.0%} LEIE exclusion rate ({excluded_count}/{member_count} facilities)"
    elif flags_triggered >= 3:
        if legitimacy["should_downgrade"] or has_strong_fp_warning:
            risk_label = "MEDIUM"
            if has_strong_fp_warning and not legitimacy["should_downgrade"]:
                classification_note = "Downgraded from HIGH due to false positive patterns detected"
            else:
                classification_note = "Downgraded from HIGH due to legitimacy signals"
        else:
            risk_label = "HIGH"
            classification_note = None
    elif flags_triggered >= 1:
        risk_label = "MEDIUM"
        classification_note = None
    else:
        risk_label = "LOW"
        classification_note = None

    result = {
        "community_id": int(community_id),
        "member_count": member_count,
        "flags_triggered": flags_triggered,
        "total_flags": 5,
        "fraud_density": round(fraud_density, 2),
        "excluded_count": excluded_count,
        "details": details,
        "risk_label": risk_label,
        "legitimacy_signals": legitimacy,
    }

    if classification_note:
        result["classification_note"] = classification_note

    if false_positive_warnings:
        result["false_positive_warnings"] = false_positive_warnings

    return result
