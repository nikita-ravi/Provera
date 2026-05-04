"""Add legitimacy features to facility_features.parquet."""
import pandas as pd
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FILTERED_DIR = PROJECT_ROOT / "data" / "filtered"


def load_enrollment_data() -> pd.DataFrame:
    """Load HHA and SNF enrollment data for incorporation dates."""
    print("\n=== Loading Enrollment Data ===")

    enrollments = []

    # HHA enrollments
    hha_path = FILTERED_DIR / "hha_enrollments_fl.parquet"
    if hha_path.exists():
        hha = pd.read_parquet(hha_path)
        hha = hha.rename(columns={
            "NPI": "npi",
            "INCORPORATION DATE": "incorporation_date",
            "PROPRIETARY_NONPROFIT": "ownership_class",
        })
        hha["npi"] = hha["npi"].astype(str).str.strip()
        enrollments.append(hha[["npi", "incorporation_date", "ownership_class"]])
        print(f"  HHA enrollments: {len(hha)} rows")

    # SNF enrollments
    snf_path = FILTERED_DIR / "snf_enrollments_fl.parquet"
    if snf_path.exists():
        snf = pd.read_parquet(snf_path)
        snf = snf.rename(columns={
            "NPI": "npi",
            "INCORPORATION DATE": "incorporation_date",
            "PROPRIETARY_NONPROFIT": "ownership_class",
        })
        snf["npi"] = snf["npi"].astype(str).str.strip()
        enrollments.append(snf[["npi", "incorporation_date", "ownership_class"]])
        print(f"  SNF enrollments: {len(snf)} rows")

    if enrollments:
        return pd.concat(enrollments, ignore_index=True).drop_duplicates(subset=["npi"])
    return pd.DataFrame()


def load_quality_data() -> pd.DataFrame:
    """Load NH Compare quality data."""
    print("\n=== Loading Quality Data ===")

    nh_path = FILTERED_DIR / "nh_providerinfo_fl.parquet"
    if not nh_path.exists():
        print("  NH Provider Info not found")
        return pd.DataFrame()

    nh = pd.read_parquet(nh_path)

    # Rename columns
    nh = nh.rename(columns={
        "CMS Certification Number (CCN)": "ccn",
        "Overall Rating": "overall_rating",
        "Health Inspection Rating": "health_rating",
        "QM Rating": "qm_rating",
        "Staffing Rating": "staffing_rating",
        "Reported Total Nurse Staffing Hours per Resident per Day": "staffing_hours",
        "Number of Fines": "num_fines",
        "Total Amount of Fines in Dollars": "total_fines",
        "Number of Payment Denials": "payment_denials",
        "Total Number of Penalties": "total_penalties",
        "Special Focus Status": "special_focus",
        "Abuse Icon": "abuse_icon",
    })

    # Select quality columns
    quality_cols = ["ccn", "overall_rating", "health_rating", "qm_rating",
                    "staffing_rating", "staffing_hours", "num_fines", "total_fines",
                    "payment_denials", "total_penalties", "special_focus", "abuse_icon"]

    nh_slim = nh[[c for c in quality_cols if c in nh.columns]].copy()
    nh_slim["ccn"] = nh_slim["ccn"].astype(str).str.strip()

    print(f"  NH Provider Info: {len(nh_slim)} rows")
    return nh_slim


def compute_entity_age(incorporation_date: str, reference_date: datetime = None) -> float:
    """Compute entity age in days from incorporation date."""
    if pd.isna(incorporation_date):
        return None

    if reference_date is None:
        reference_date = datetime.now()

    try:
        # Handle MM/DD/YYYY format
        inc_date = pd.to_datetime(incorporation_date, format="%m/%d/%Y", errors="coerce")
        if pd.isna(inc_date):
            inc_date = pd.to_datetime(incorporation_date, errors="coerce")
        if pd.isna(inc_date):
            return None
        return (reference_date - inc_date).days
    except:
        return None


def add_legitimacy_features():
    """Add legitimacy features to facility_features.parquet."""
    print("=" * 60)
    print("ADDING LEGITIMACY FEATURES")
    print("=" * 60)

    # Load existing features
    features = pd.read_parquet(PROCESSED_DIR / "facility_features.parquet")
    master = pd.read_parquet(PROCESSED_DIR / "master_facilities.parquet")

    print(f"\nExisting features: {len(features)} rows, {len(features.columns)} columns")
    features["npi"] = features["npi"].astype(str).str.strip()
    master["npi"] = master["npi"].astype(str).str.strip()

    # Merge master for existing fields
    features = features.merge(
        master[["npi", "ccn", "star_rating", "ownership_type"]],
        on="npi",
        how="left",
        suffixes=("", "_master")
    )

    # Load enrollment data
    enrollments = load_enrollment_data()
    if not enrollments.empty:
        features = features.merge(enrollments, on="npi", how="left")

    # Load quality data and merge via CCN
    quality = load_quality_data()
    if not quality.empty and "ccn" in features.columns:
        features["ccn"] = features["ccn"].astype(str).str.strip()
        features = features.merge(quality, on="ccn", how="left", suffixes=("", "_quality"))

    # === COMPUTE LEGITIMACY FEATURES ===
    print("\n=== Computing Legitimacy Features ===")

    # 1. Entity age in days
    print("  Computing entity_age_days...")
    features["entity_age_days"] = features["incorporation_date"].apply(compute_entity_age)
    age_available = features["entity_age_days"].notna().sum()
    print(f"    Facilities with age data: {age_available}")

    # 2. Is nonprofit
    print("  Computing is_nonprofit...")
    features["is_nonprofit"] = (
        features["ownership_type"].str.lower().str.contains("non profit|nonprofit|non-profit", na=False) |
        features["ownership_class"].str.lower().str.contains("non-profit|nonprofit", na=False)
    ).astype(int)
    nonprofit_count = features["is_nonprofit"].sum()
    print(f"    Nonprofit facilities: {nonprofit_count}")

    # 3. Has star rating
    print("  Computing has_star_rating...")
    features["has_star_rating"] = features["star_rating"].notna().astype(int)
    rated_count = features["has_star_rating"].sum()
    print(f"    Facilities with star rating: {rated_count}")

    # 4. Has quality data (any quality rating available)
    print("  Computing has_quality_data...")
    quality_cols = ["overall_rating", "health_rating", "qm_rating", "staffing_rating"]
    existing_quality_cols = [c for c in quality_cols if c in features.columns]
    if existing_quality_cols:
        features["has_quality_data"] = features[existing_quality_cols].notna().any(axis=1).astype(int)
    else:
        features["has_quality_data"] = 0
    quality_count = features["has_quality_data"].sum()
    print(f"    Facilities with quality data: {quality_count}")

    # 5. Staffing ratio (normalized)
    print("  Computing staffing_ratio...")
    if "staffing_hours" in features.columns:
        features["staffing_ratio"] = pd.to_numeric(features["staffing_hours"], errors="coerce")
        # Normalize to 0-1 scale
        max_staffing = features["staffing_ratio"].max()
        if max_staffing > 0:
            features["staffing_ratio"] = features["staffing_ratio"] / max_staffing
    else:
        features["staffing_ratio"] = 0.0

    # 6. Has penalties (negative signal)
    print("  Computing has_penalties...")
    if "total_penalties" in features.columns:
        features["has_penalties"] = (pd.to_numeric(features["total_penalties"], errors="coerce") > 0).astype(int)
    else:
        features["has_penalties"] = 0
    penalties_count = features["has_penalties"].sum()
    print(f"    Facilities with penalties: {penalties_count}")

    # 7. Entity age buckets (useful for model)
    print("  Computing entity_age_years...")
    features["entity_age_years"] = features["entity_age_days"] / 365.25
    features["entity_age_years"] = features["entity_age_years"].fillna(0)

    # Fill NaN for new features
    features["entity_age_days"] = features["entity_age_days"].fillna(0)
    features["is_nonprofit"] = features["is_nonprofit"].fillna(0)
    features["has_star_rating"] = features["has_star_rating"].fillna(0)
    features["has_quality_data"] = features["has_quality_data"].fillna(0)
    features["staffing_ratio"] = features["staffing_ratio"].fillna(0)
    features["has_penalties"] = features["has_penalties"].fillna(0)

    # Drop intermediate columns
    drop_cols = ["incorporation_date", "ownership_class", "ownership_type",
                 "star_rating", "ccn", "overall_rating", "health_rating",
                 "qm_rating", "staffing_rating", "staffing_hours",
                 "num_fines", "total_fines", "payment_denials",
                 "total_penalties", "special_focus", "abuse_icon"]
    features = features.drop(columns=[c for c in drop_cols if c in features.columns], errors="ignore")

    # Summary
    print(f"\n=== Feature Summary ===")
    print(f"Final features: {len(features)} rows, {len(features.columns)} columns")
    print(f"\nNew legitimacy features:")
    new_features = ["entity_age_days", "entity_age_years", "is_nonprofit",
                    "has_star_rating", "has_quality_data", "staffing_ratio", "has_penalties"]
    for feat in new_features:
        if feat in features.columns:
            print(f"  {feat}: mean={features[feat].mean():.3f}, non-zero={features[feat].gt(0).sum()}")

    # Save updated features
    output_path = PROCESSED_DIR / "facility_features.parquet"
    features.to_parquet(output_path, index=False)
    print(f"\nSaved to: {output_path}")

    return features


if __name__ == "__main__":
    add_legitimacy_features()
