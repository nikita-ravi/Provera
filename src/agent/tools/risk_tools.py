"""Risk score and SHAP explanation tools."""
import pandas as pd
from pathlib import Path
from functools import lru_cache

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@lru_cache(maxsize=1)
def _load_shap_values() -> pd.DataFrame:
    """Load SHAP values (cached)."""
    return pd.read_parquet(PROCESSED_DIR / "shap_values.parquet")


@lru_cache(maxsize=1)
def _load_features() -> pd.DataFrame:
    """Load facility features (cached)."""
    return pd.read_parquet(PROCESSED_DIR / "facility_features.parquet")


# Feature names that map to SHAP columns
FEATURE_NAMES = [
    "total_charges", "total_payments", "total_beneficiaries",
    "charges_per_beneficiary", "payment_to_charge_ratio", "avg_payment_per_beneficiary",
    "pagerank", "degree_centrality", "clustering_coeff", "betweenness_centrality",
    "degree", "louvain_community", "community_size", "neighbor_count",
    "owner_count", "max_owner_facility_count", "total_owner_facility_count",
    "shared_address_count", "shared_phone_count"
]


def get_shap_explanation(npi: str, top_n: int = 5) -> list:
    """
    Returns top SHAP feature contributions for a facility's risk score.

    Output: list of {
        "feature": str,
        "value": float,
        "shap_contribution": float,
        "direction": "increases_risk" or "decreases_risk",
    }
    """
    shap_df = _load_shap_values()
    features_df = _load_features()

    npi_str = str(npi).strip()

    # Find SHAP row for this NPI
    shap_row = shap_df[shap_df["npi"].astype(str) == npi_str]

    if shap_row.empty:
        return [{"error": f"SHAP values not found for NPI {npi}"}]

    shap_row = shap_row.iloc[0]

    # Find feature row
    feature_row = features_df[features_df["npi"].astype(str) == npi_str]

    if feature_row.empty:
        return [{"error": f"Features not found for NPI {npi}"}]

    feature_row = feature_row.iloc[0]

    # Collect SHAP values with feature values
    shap_contributions = []

    for feature in FEATURE_NAMES:
        shap_col = f"shap_{feature}"

        if shap_col in shap_row.index:
            shap_value = float(shap_row[shap_col])
            feature_value = float(feature_row.get(feature, 0)) if pd.notna(feature_row.get(feature)) else 0

            shap_contributions.append({
                "feature": feature,
                "value": feature_value,
                "shap_contribution": shap_value,
                "direction": "increases_risk" if shap_value > 0 else "decreases_risk",
            })

    # Sort by absolute SHAP value descending
    shap_contributions.sort(key=lambda x: abs(x["shap_contribution"]), reverse=True)

    # Return top N
    return shap_contributions[:top_n]


def get_risk_score(npi: str) -> dict:
    """
    Get the fraud risk score for a facility.

    Output: {
        "npi": str,
        "fraud_risk_score": float,
        "risk_percentile": float,
        "risk_tier": "HIGH" or "MEDIUM" or "LOW",
    }
    """
    features_df = _load_features()

    npi_str = str(npi).strip()

    row = features_df[features_df["npi"].astype(str) == npi_str]

    if row.empty:
        return {"error": f"Facility with NPI {npi} not found"}

    score = float(row.iloc[0]["fraud_risk_score"])

    # Calculate percentile
    all_scores = features_df["fraud_risk_score"].values
    percentile = (all_scores < score).sum() / len(all_scores) * 100

    # Determine tier
    if score >= 0.6:
        tier = "HIGH"
    elif score >= 0.3:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return {
        "npi": npi_str,
        "fraud_risk_score": score,
        "risk_percentile": float(percentile),
        "risk_tier": tier,
    }
