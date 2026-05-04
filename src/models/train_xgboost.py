"""Train XGBoost risk scorer with cross-validation and SHAP explanations."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import shap
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    roc_auc_score, average_precision_score, precision_recall_curve,
    f1_score, classification_report, confusion_matrix
)
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
OUTPUTS_DIR = PROJECT_ROOT / "medigraph" / "outputs"

# Feature groups
BILLING_FEATURES = [
    'total_charges', 'total_payments', 'total_beneficiaries',
    'charges_per_beneficiary', 'payment_to_charge_ratio', 'avg_payment_per_beneficiary'
]

# NOTE: community_fraud_density, fraud_neighbor_ratio, and community_excluded_count
# are EXCLUDED from training - they use is_excluded in their computation (data leakage).
# These features are still computed for the agent's red-flag checklist at inference time.
GRAPH_FEATURES = [
    'pagerank', 'degree_centrality', 'clustering_coeff', 'betweenness_centrality',
    'degree', 'louvain_community', 'community_size', 'neighbor_count'
]

OWNERSHIP_FEATURES = [
    'owner_count', 'max_owner_facility_count', 'total_owner_facility_count',
    'shared_address_count', 'shared_phone_count'
]

# Legitimacy features - help distinguish fraud from legitimate clustering
LEGITIMACY_FEATURES = [
    'entity_age_days', 'entity_age_years', 'is_nonprofit',
    'has_star_rating', 'has_quality_data', 'staffing_ratio', 'has_penalties'
]


def load_features() -> pd.DataFrame:
    """Load feature matrix."""
    print("=== Loading Features ===")
    df = pd.read_parquet(PROCESSED_DIR / "facility_features.parquet")
    print(f"  Loaded {len(df):,} facilities")
    print(f"  Features: {len(df.columns)}")
    print(f"  Excluded: {df['is_excluded'].sum():,} ({df['is_excluded'].mean()*100:.2f}%)")
    return df


def prepare_data(df: pd.DataFrame, feature_cols: list):
    """Prepare X, y for training."""
    X = df[feature_cols].copy()
    y = df['is_excluded'].astype(int)

    # Fill NaN and infinity
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(0)

    return X, y


def evaluate_model(model, X, y, cv=5) -> dict:
    """Evaluate model with stratified cross-validation."""
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)

    metrics = {
        'auc_roc': [],
        'auc_pr': [],
        'f1': [],
        'precision': [],
        'recall': []
    }

    y_pred_all = np.zeros(len(y))
    y_proba_all = np.zeros(len(y))

    for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        y_proba = model.predict_proba(X_val)[:, 1]
        y_pred = (y_proba >= 0.5).astype(int)

        y_pred_all[val_idx] = y_pred
        y_proba_all[val_idx] = y_proba

        metrics['auc_roc'].append(roc_auc_score(y_val, y_proba))
        metrics['auc_pr'].append(average_precision_score(y_val, y_proba))
        metrics['f1'].append(f1_score(y_val, y_pred))

        prec, rec, _ = precision_recall_curve(y_val, y_proba)
        metrics['precision'].append(np.mean(prec))
        metrics['recall'].append(np.mean(rec))

    # Compute mean and std
    results = {}
    for metric, values in metrics.items():
        results[f'{metric}_mean'] = np.mean(values)
        results[f'{metric}_std'] = np.std(values)

    results['y_pred'] = y_pred_all
    results['y_proba'] = y_proba_all

    return results


def train_model_variants(df: pd.DataFrame) -> dict:
    """Train three model variants and compare."""
    print("\n=== Training Model Variants ===")

    # Calculate class weight
    n_neg = (df['is_excluded'] == 0).sum()
    n_pos = (df['is_excluded'] == 1).sum()
    scale_pos_weight = n_neg / n_pos
    print(f"  Class imbalance: {n_neg}:{n_pos} (scale_pos_weight={scale_pos_weight:.1f})")

    results = {}

    # Model 1: Billing only
    print("\n  Training billing_only model...")
    X_billing, y = prepare_data(df, BILLING_FEATURES)
    model_billing = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        random_state=42
    )
    results['billing_only'] = evaluate_model(model_billing, X_billing, y)
    results['billing_only']['features'] = BILLING_FEATURES

    # Model 2: Billing + Graph
    print("  Training billing_plus_graph model...")
    billing_graph_features = BILLING_FEATURES + GRAPH_FEATURES
    X_graph, y = prepare_data(df, billing_graph_features)
    model_graph = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        random_state=42,
            )
    results['billing_plus_graph'] = evaluate_model(model_graph, X_graph, y)
    results['billing_plus_graph']['features'] = billing_graph_features

    # Model 3: Billing + Graph + Ownership (no legitimacy)
    print("  Training billing_graph_ownership model...")
    bgo_features = BILLING_FEATURES + GRAPH_FEATURES + OWNERSHIP_FEATURES
    bgo_features = list(dict.fromkeys(bgo_features))
    X_bgo, y = prepare_data(df, bgo_features)
    model_bgo = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        random_state=42,
    )
    results['billing_graph_ownership'] = evaluate_model(model_bgo, X_bgo, y)
    results['billing_graph_ownership']['features'] = bgo_features

    # Model 4: Full (All features including legitimacy)
    print("  Training full model (with legitimacy features)...")
    all_features = BILLING_FEATURES + GRAPH_FEATURES + OWNERSHIP_FEATURES + LEGITIMACY_FEATURES
    # Remove duplicates
    all_features = list(dict.fromkeys(all_features))
    # Filter to only features that exist in the dataframe
    all_features = [f for f in all_features if f in df.columns]
    X_full, y = prepare_data(df, all_features)
    model_full = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        random_state=42,
    )
    results['full'] = evaluate_model(model_full, X_full, y)
    results['full']['features'] = all_features
    results['full']['model'] = model_full

    return results, X_full, y


def print_comparison(results: dict):
    """Print model comparison table."""
    print("\n=== Model Comparison ===")
    print(f"{'Model':<20} {'AUC-ROC':>10} {'AUC-PR':>10} {'F1':>10}")
    print("-" * 52)

    for name, res in results.items():
        if name == 'full':
            continue
        print(f"{name:<20} {res['auc_roc_mean']:.4f}±{res['auc_roc_std']:.3f} "
              f"{res['auc_pr_mean']:.4f}±{res['auc_pr_std']:.3f} "
              f"{res['f1_mean']:.4f}±{res['f1_std']:.3f}")

    res = results['full']
    print(f"{'full':<20} {res['auc_roc_mean']:.4f}±{res['auc_roc_std']:.3f} "
          f"{res['auc_pr_mean']:.4f}±{res['auc_pr_std']:.3f} "
          f"{res['f1_mean']:.4f}±{res['f1_std']:.3f}")

    # Improvement from features
    billing_auc = results['billing_only']['auc_roc_mean']
    graph_auc = results['billing_plus_graph']['auc_roc_mean']
    bgo_auc = results.get('billing_graph_ownership', {}).get('auc_roc_mean', graph_auc)
    full_auc = results['full']['auc_roc_mean']

    print(f"\n  Graph features improvement: +{(graph_auc - billing_auc)*100:.1f}% AUC-ROC")
    print(f"  Ownership features improvement: +{(bgo_auc - graph_auc)*100:.1f}% AUC-ROC")
    print(f"  Legitimacy features improvement: +{(full_auc - bgo_auc)*100:.1f}% AUC-ROC")
    print(f"  Total improvement: +{(full_auc - billing_auc)*100:.1f}% AUC-ROC")


def save_comparison(results: dict, output_path: Path):
    """Save model comparison to CSV."""
    rows = []
    for name, res in results.items():
        rows.append({
            'model': name,
            'auc_roc_mean': res['auc_roc_mean'],
            'auc_roc_std': res['auc_roc_std'],
            'auc_pr_mean': res['auc_pr_mean'],
            'auc_pr_std': res['auc_pr_std'],
            'f1_mean': res['f1_mean'],
            'f1_std': res['f1_std'],
            'n_features': len(res.get('features', []))
        })

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"  Saved comparison to {output_path}")


def train_final_model(X: pd.DataFrame, y: pd.Series, scale_pos_weight: float):
    """Train final model on all data."""
    print("\n=== Training Final Model ===")

    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        eval_metric='aucpr',
        random_state=42,
            )

    model.fit(X, y, verbose=False)
    print(f"  Trained on {len(X):,} samples with {len(X.columns)} features")

    return model


def compute_shap_values(model, X: pd.DataFrame) -> np.ndarray:
    """Compute SHAP values for all samples."""
    print("\n=== Computing SHAP Values ===")

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    print(f"  SHAP values shape: {shap_values.shape}")

    return shap_values


def save_shap_summary_plot(shap_values: np.ndarray, X: pd.DataFrame, output_path: Path):
    """Save SHAP summary plot."""
    print("  Generating SHAP summary plot...")

    plt.figure(figsize=(10, 8))
    shap.summary_plot(shap_values, X, show=False, max_display=20)
    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"  Saved SHAP summary to {output_path}")


def print_top_features(shap_values: np.ndarray, X: pd.DataFrame, n=10):
    """Print top features by mean absolute SHAP value."""
    print(f"\n=== Top {n} Features by SHAP Importance ===")

    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    feature_importance = pd.DataFrame({
        'feature': X.columns,
        'importance': mean_abs_shap
    }).sort_values('importance', ascending=False)

    for i, row in feature_importance.head(n).iterrows():
        print(f"  {row['feature']:<30} {row['importance']:.4f}")

    return feature_importance


def save_model(model, output_path: Path):
    """Save XGBoost model."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(output_path))
    print(f"  Saved model to {output_path}")


def save_risk_scores(df: pd.DataFrame, model, X: pd.DataFrame, output_path: Path):
    """Add risk scores to feature DataFrame and save."""
    print("\n=== Saving Risk Scores ===")

    # Get probabilities
    risk_scores = model.predict_proba(X)[:, 1]

    # Add to DataFrame
    df_out = df.copy()
    df_out['fraud_risk_score'] = risk_scores

    df_out.to_parquet(output_path, index=False)
    print(f"  Saved {len(df_out):,} facilities with risk scores")

    # Print risk score distribution
    print(f"\n  Risk score distribution:")
    print(f"    Min: {risk_scores.min():.4f}")
    print(f"    Max: {risk_scores.max():.4f}")
    print(f"    Mean: {risk_scores.mean():.4f}")
    print(f"    Median: {np.median(risk_scores):.4f}")

    # Top 10 highest risk
    print(f"\n  Top 10 highest risk facilities:")
    top10 = df_out.nlargest(10, 'fraud_risk_score')[['npi', 'fraud_risk_score', 'is_excluded', 'provider_type']]
    for _, row in top10.iterrows():
        excluded = "EXCLUDED" if row['is_excluded'] else ""
        print(f"    NPI {row['npi']}: {row['fraud_risk_score']:.4f} {row['provider_type']} {excluded}")


def save_shap_values(shap_values: np.ndarray, X: pd.DataFrame, df: pd.DataFrame, output_path: Path):
    """Save SHAP values to parquet."""
    shap_df = pd.DataFrame(shap_values, columns=[f"shap_{c}" for c in X.columns])
    shap_df['npi'] = df['npi'].values
    shap_df.to_parquet(output_path, index=False)
    print(f"  Saved SHAP values to {output_path}")


def train_and_evaluate():
    """Main training pipeline."""
    # Load features
    df = load_features()

    # Train model variants
    results, X_full, y = train_model_variants(df)

    # Print comparison
    print_comparison(results)

    # Save comparison
    save_comparison(results, OUTPUTS_DIR / "model_comparison.csv")

    # Train final model on all data
    n_neg = (y == 0).sum()
    n_pos = (y == 1).sum()
    scale_pos_weight = n_neg / n_pos

    final_model = train_final_model(X_full, y, scale_pos_weight)

    # Save model
    save_model(final_model, MODELS_DIR / "xgboost_full.json")

    # Compute SHAP values
    shap_values = compute_shap_values(final_model, X_full)

    # Save SHAP summary plot
    save_shap_summary_plot(shap_values, X_full, OUTPUTS_DIR / "shap_summary.png")

    # Print top features
    feature_importance = print_top_features(shap_values, X_full)

    # Save SHAP values
    save_shap_values(shap_values, X_full, df, PROCESSED_DIR / "shap_values.parquet")

    # Save risk scores
    save_risk_scores(df, final_model, X_full, PROCESSED_DIR / "facility_features.parquet")

    print("\n=== Training Complete ===")

    return final_model, results


if __name__ == "__main__":
    train_and_evaluate()
