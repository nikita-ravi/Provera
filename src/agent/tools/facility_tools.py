"""Facility lookup tools."""
import pandas as pd
from pathlib import Path
from functools import lru_cache

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@lru_cache(maxsize=1)
def _load_facility_data() -> pd.DataFrame:
    """Load and merge facility data (cached)."""
    features = pd.read_parquet(PROCESSED_DIR / "facility_features.parquet")
    master = pd.read_parquet(PROCESSED_DIR / "master_facilities.parquet")

    # Columns to merge from master (including new enrichment fields)
    master_cols = [
        "npi", "ccn", "facility_name", "address", "phone",
        "ownership_type", "star_rating", "exclusion_date", "exclusion_type",
        # New enrichment fields
        "linked_exclusion_type", "excluded_individual_name",
        "billing_change_pct", "ownership_churn_count", "owner_count",
        "sunbiz_status", "sunbiz_filing_date", "sunbiz_entity_age_years"
    ]

    # Only include columns that exist in master
    master_cols = [c for c in master_cols if c in master.columns]

    # Merge on NPI
    merged = features.merge(
        master[master_cols],
        on="npi",
        how="left",
        suffixes=("", "_master")
    )
    return merged


def get_facility_profile(npi: str) -> dict:
    """
    Returns complete profile for a facility.

    Output: {
        "npi": str,
        "ccn": str or None,
        "facility_name": str,
        "address": str,
        "phone": str,
        "provider_type": "SNF" or "HHA",
        "ownership_type": str,
        "star_rating": str or None,
        "total_charges": float or None,
        "total_payments": float or None,
        "total_beneficiaries": int or None,
        "avg_payment_per_beneficiary": float or None,
        "fraud_risk_score": float,
        "is_excluded": bool,
        "exclusion_type": str or None (OWNER_LINKED, NPPES_LINKED, or original LEIE code),
        "exclusion_date": str or None,
        # Enhanced exclusion info
        "linked_exclusion_type": str or None (original LEIE code like 1128a1 for linked exclusions),
        "excluded_individual_name": str or None (name of excluded individual for linked exclusions),
        # Billing trajectory
        "billing_change_pct": float or None (YoY % change in Medicare payments),
        # Ownership stability
        "ownership_churn_count": int or None (number of distinct ownership changes),
        "owner_count": int or None (total number of distinct owners),
        # Sunbiz corporate status
        "sunbiz_status": str or None (ACTIVE, INACTIVE, DISSOLVED, NOT_FOUND),
        "sunbiz_filing_date": str or None (incorporation date),
        "sunbiz_entity_age_years": float or None (years since incorporation),
        # Legitimacy indicators
        "entity_age_years": float or None,
        "is_nonprofit": bool,
        "has_star_rating": bool,
        "has_quality_data": bool,
    }
    """
    df = _load_facility_data()
    npi_str = str(npi).strip()

    row = df[df["npi"].astype(str) == npi_str]

    if row.empty:
        return {"error": f"Facility with NPI {npi} not found"}

    row = row.iloc[0]

    def safe_float(val):
        try:
            if pd.isna(val) or val == 0:
                return None
            return float(val)
        except:
            return None

    def safe_int(val):
        try:
            if pd.isna(val) or val == 0:
                return None
            return int(val)
        except:
            return None

    def safe_str(val):
        if pd.isna(val):
            return None
        return str(val).strip() if str(val).strip() else None

    # Compute entity age in years for display
    entity_age_days = row.get("entity_age_days", 0)
    entity_age_years = round(entity_age_days / 365.25, 1) if entity_age_days and entity_age_days > 0 else None

    return {
        "npi": str(row["npi"]),
        "ccn": safe_str(row.get("ccn")),
        "facility_name": safe_str(row.get("facility_name", "Unknown")),
        "address": safe_str(row.get("address")),
        "phone": safe_str(row.get("phone")),
        "provider_type": safe_str(row.get("provider_type", "Unknown")),
        "ownership_type": safe_str(row.get("ownership_type")),
        "star_rating": safe_str(row.get("star_rating")),
        "total_charges": safe_float(row.get("total_charges")),
        "total_payments": safe_float(row.get("total_payments")),
        "total_beneficiaries": safe_int(row.get("total_beneficiaries")),
        "avg_payment_per_beneficiary": safe_float(row.get("avg_payment_per_beneficiary")),
        "fraud_risk_score": float(row.get("fraud_risk_score", 0)),
        "is_excluded": bool(row.get("is_excluded", False)),
        "exclusion_type": safe_str(row.get("exclusion_type")),
        "exclusion_date": safe_str(row.get("exclusion_date")),
        # Enhanced exclusion info (original LEIE reason for linked exclusions)
        "linked_exclusion_type": safe_str(row.get("linked_exclusion_type")),
        "excluded_individual_name": safe_str(row.get("excluded_individual_name")),
        # Billing trajectory (YoY change)
        "billing_change_pct": safe_float(row.get("billing_change_pct")),
        # Ownership stability indicators
        "ownership_churn_count": safe_int(row.get("ownership_churn_count")),
        "owner_count": safe_int(row.get("owner_count")),
        # Sunbiz corporate status (if available)
        "sunbiz_status": safe_str(row.get("sunbiz_status")),
        "sunbiz_filing_date": safe_str(row.get("sunbiz_filing_date")),
        "sunbiz_entity_age_years": safe_float(row.get("sunbiz_entity_age_years")),
        # Legitimacy indicators
        "entity_age_years": entity_age_years,
        "is_nonprofit": bool(row.get("is_nonprofit", 0)),
        "has_star_rating": bool(row.get("has_star_rating", 0)),
        "has_quality_data": bool(row.get("has_quality_data", 0)),
    }


def get_billing_comparison(npi: str) -> dict:
    """
    Compare facility billing to state median.

    Output: {
        "npi": str,
        "facility_avg_per_bene": float or None,
        "state_median_per_bene": float,
        "deviation_sigma": float or None,
        "deviation_pct": float or None,
    }
    """
    df = _load_facility_data()
    npi_str = str(npi).strip()

    row = df[df["npi"].astype(str) == npi_str]

    if row.empty:
        return {"error": f"Facility with NPI {npi} not found"}

    row = row.iloc[0]

    # Calculate state median (only for facilities with billing data)
    billing_df = df[df["avg_payment_per_beneficiary"] > 0]
    state_median = billing_df["avg_payment_per_beneficiary"].median()
    state_std = billing_df["avg_payment_per_beneficiary"].std()

    facility_avg = row.get("avg_payment_per_beneficiary")

    if pd.isna(facility_avg) or facility_avg == 0:
        return {
            "npi": npi_str,
            "facility_avg_per_bene": None,
            "state_median_per_bene": float(state_median),
            "deviation_sigma": None,
            "deviation_pct": None,
        }

    deviation_sigma = (facility_avg - state_median) / state_std if state_std > 0 else 0
    deviation_pct = ((facility_avg - state_median) / state_median) * 100

    return {
        "npi": npi_str,
        "facility_avg_per_bene": float(facility_avg),
        "state_median_per_bene": float(state_median),
        "deviation_sigma": float(deviation_sigma),
        "deviation_pct": float(deviation_pct),
    }
