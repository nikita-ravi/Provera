#!/usr/bin/env python3
"""
MediGraph Week 2 Pipeline

Orchestrates:
1. Graph construction
2. Facility projection
3. Feature engineering
4. XGBoost training + evaluation
"""
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.build_graph import build_and_save as build_graph
from src.graph.project_graph import project_and_save as project_graph
from src.graph.compute_features import compute_all_features
from src.models.train_xgboost import train_and_evaluate


def verify_outputs():
    """Verify all expected outputs exist."""
    print("\n" + "=" * 60)
    print("VERIFICATION CHECKLIST")
    print("=" * 60)

    PROJECT_ROOT = Path(__file__).parent.parent.parent
    PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
    MODELS_DIR = PROJECT_ROOT / "models"
    OUTPUTS_DIR = PROJECT_ROOT / "medigraph" / "outputs"

    files = [
        (PROCESSED_DIR / "medigraph.gpickle", "Heterogeneous graph"),
        (PROCESSED_DIR / "facility_graph.gpickle", "Facility projection"),
        (PROCESSED_DIR / "facility_features.parquet", "Feature matrix with risk scores"),
        (PROCESSED_DIR / "shap_values.parquet", "SHAP values"),
        (MODELS_DIR / "xgboost_full.json", "XGBoost model"),
        (OUTPUTS_DIR / "model_comparison.csv", "Model comparison"),
        (OUTPUTS_DIR / "shap_summary.png", "SHAP summary plot"),
    ]

    all_exist = True
    for path, desc in files:
        if path.exists():
            size = path.stat().st_size
            if size > 1024 * 1024:
                size_str = f"{size / (1024*1024):.2f} MB"
            else:
                size_str = f"{size / 1024:.1f} KB"
            print(f"  ✓ {desc}: {size_str}")
        else:
            print(f"  ✗ {desc}: MISSING")
            all_exist = False

    return all_exist


def run_pipeline():
    """Run the complete Week 2 pipeline."""
    start_time = time.time()

    print("=" * 60)
    print("MEDIGRAPH WEEK 2 PIPELINE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: Build graph
    print("\n" + "=" * 60)
    print("STEP 1: BUILD HETEROGENEOUS GRAPH")
    print("=" * 60)
    build_graph()

    # Step 2: Project to facility graph
    print("\n" + "=" * 60)
    print("STEP 2: PROJECT TO FACILITY GRAPH")
    print("=" * 60)
    project_graph()

    # Step 3: Compute features
    print("\n" + "=" * 60)
    print("STEP 3: COMPUTE GRAPH FEATURES")
    print("=" * 60)
    compute_all_features()

    # Step 4: Train XGBoost
    print("\n" + "=" * 60)
    print("STEP 4: TRAIN XGBOOST RISK SCORER")
    print("=" * 60)
    train_and_evaluate()

    # Verify outputs
    all_exist = verify_outputs()

    # Summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print(f"Total time: {elapsed / 60:.1f} minutes")
    if all_exist:
        print("All outputs verified ✓")
    else:
        print("WARNING: Some outputs missing")
    print("=" * 60)


if __name__ == "__main__":
    run_pipeline()
