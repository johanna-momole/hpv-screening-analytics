"""
No-show prediction model for the HPV Screening Analytics Platform.

Uses logistic regression as the primary model (interpretable coefficients)
and a decision tree as a secondary model (visual rule extraction).
All results are derived from synthetic data and do not represent real
clinical predictions or population behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.tree import DecisionTreeClassifier
from sklearn.utils.class_weight import compute_sample_weight

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hpv_screening.db"

NUMERIC_FEATURES  = ["age", "lead_time_days"]
CATEGORICAL_FEATURES = [
    "gender", "ethnicity", "education_level",
    "coverage_type", "facility_type", "specialty",
]
TARGET = "no_show"

FEATURE_DISPLAY_NAMES = {
    "age":                   "Patient Age",
    "lead_time_days":        "Lead Time (days)",
    "gender_M":              "Gender: Male",
    "gender_F":              "Gender: Female",
    "coverage_type_Self-Pay": "Insurance: Self-Pay",
    "coverage_type_Medicaid": "Insurance: Medicaid",
    "coverage_type_ACA":     "Insurance: ACA",
    "coverage_type_Private": "Insurance: Private",
    "coverage_type_Medicare": "Insurance: Medicare",
    "education_level_Less than High School": "Edu: < High School",
    "education_level_High School":          "Edu: High School",
    "education_level_Some College":         "Edu: Some College",
    "education_level_Associate":            "Edu: Associate",
    "education_level_Bachelor":             "Edu: Bachelor",
    "education_level_Graduate":             "Edu: Graduate",
    "facility_type_FQHC":                   "Facility: FQHC",
    "facility_type_Community Health Center": "Facility: Community HC",
    "facility_type_Hospital Outpatient":    "Facility: Hospital OP",
    "facility_type_Private Practice":       "Facility: Private Practice",
    "facility_type_Reproductive Health Clinic": "Facility: Repro Health",
    "facility_type_Academic Outpatient":    "Facility: Academic",
}


def prepare_features(master: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES + [TARGET]
    df = master[cols].dropna(subset=[TARGET] + NUMERIC_FEATURES)

    # Impute rare missing categoricals with 'Unknown'
    for c in CATEGORICAL_FEATURES:
        df[c] = df[c].fillna("Unknown").astype(str)

    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET].astype(int)
    return X, y


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ]
    )


def build_pipeline(model: Any = None) -> Pipeline:
    if model is None:
        model = LogisticRegression(
            C=1.0,
            max_iter=1000,
            class_weight="balanced",
            random_state=42,
            solver="lbfgs",
        )
    return Pipeline([
        ("preprocessor", build_preprocessor()),
        ("classifier",   model),
    ])


def get_feature_names(pipeline: Pipeline) -> list[str]:
    """Extract one-hot encoded feature names from fitted pipeline."""
    preproc = pipeline.named_steps["preprocessor"]
    num_names = NUMERIC_FEATURES
    cat_names = list(preproc.named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES))
    return num_names + cat_names


def extract_coefficients(pipeline: Pipeline) -> pd.DataFrame:
    """Return a DataFrame of logistic regression coefficients with display names."""
    feature_names = get_feature_names(pipeline)
    coefs = pipeline.named_steps["classifier"].coef_[0]

    df = pd.DataFrame({
        "feature":    feature_names,
        "coefficient": coefs,
        "display_name": [FEATURE_DISPLAY_NAMES.get(f, f) for f in feature_names],
    })
    df["abs_coef"] = df["coefficient"].abs()
    return df.sort_values("abs_coef", ascending=False).reset_index(drop=True)


def train_and_evaluate(master: pd.DataFrame) -> dict:
    """
    Train logistic regression and decision tree, evaluate with cross-validation.
    Returns a results dict with trained pipelines, metrics, and coefficient table.
    """
    X, y = prepare_features(master)

    print(f"\nTraining on {len(X):,} appointments  |  No-show rate: {y.mean():.1%}")

    # ── Logistic Regression ──────────────────────────────────────────────────
    lr_pipe = build_pipeline()
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    lr_auc_scores = cross_val_score(lr_pipe, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)

    lr_pipe.fit(X, y)
    y_prob_lr = lr_pipe.predict_proba(X)[:, 1]
    y_pred_lr = lr_pipe.predict(X)

    # ── Decision Tree (for interpretability / rule extraction) ────────────────
    dt_pipe = build_pipeline(
        model=DecisionTreeClassifier(
            max_depth=4,
            min_samples_leaf=20,
            class_weight="balanced",
            random_state=42,
        )
    )
    dt_auc_scores = cross_val_score(dt_pipe, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
    dt_pipe.fit(X, y)
    y_prob_dt = dt_pipe.predict_proba(X)[:, 1]

    coef_df = extract_coefficients(lr_pipe)

    results = {
        "lr_pipeline":      lr_pipe,
        "dt_pipeline":      dt_pipe,
        "X":                X,
        "y":                y,
        "y_prob_lr":        y_prob_lr,
        "y_pred_lr":        y_pred_lr,
        "lr_cv_auc_mean":   float(lr_auc_scores.mean()),
        "lr_cv_auc_std":    float(lr_auc_scores.std()),
        "lr_auc":           float(roc_auc_score(y, y_prob_lr)),
        "lr_ap":            float(average_precision_score(y, y_prob_lr)),
        "dt_cv_auc_mean":   float(dt_auc_scores.mean()),
        "dt_cv_auc_std":    float(dt_auc_scores.std()),
        "dt_auc":           float(roc_auc_score(y, y_prob_dt)),
        "confusion_matrix": confusion_matrix(y, y_pred_lr),
        "classification_report": classification_report(y, y_pred_lr),
        "coefficients":     coef_df,
        "feature_names":    get_feature_names(lr_pipe),
    }
    return results


def predict_individual(pipeline: Pipeline, patient_data: dict) -> float:
    """
    Predict no-show probability for a single patient record.
    patient_data keys: age, lead_time_days, gender, ethnicity, education_level,
                       coverage_type, facility_type, specialty
    """
    df = pd.DataFrame([patient_data])
    prob = pipeline.predict_proba(df)[0, 1]
    return float(prob)


def risk_tier(prob: float) -> tuple[str, str]:
    """Return (tier_label, color) for Streamlit display."""
    if prob < 0.10:
        return "Low Risk", "green"
    elif prob < 0.20:
        return "Moderate Risk", "orange"
    else:
        return "High Risk", "red"


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from src.metrics import load_all, build_master  # noqa: E402

    dfs    = load_all(DB_PATH)
    master = build_master(dfs)
    res    = train_and_evaluate(master)

    print(f"\n── Logistic Regression ─────────────────────────────────")
    print(f"  CV AUC (5-fold): {res['lr_cv_auc_mean']:.3f} ± {res['lr_cv_auc_std']:.3f}")
    print(f"  Train AUC:       {res['lr_auc']:.3f}")
    print(f"  Avg Precision:   {res['lr_ap']:.3f}")
    print(f"\n── Decision Tree ───────────────────────────────────────")
    print(f"  CV AUC (5-fold): {res['dt_cv_auc_mean']:.3f} ± {res['dt_cv_auc_std']:.3f}")
    print(f"\n── Top 10 Coefficients (Logistic Regression) ───────────")
    print(res["coefficients"][["display_name", "coefficient"]].head(10).to_string(index=False))
    print(f"\n── Classification Report ───────────────────────────────")
    print(res["classification_report"])
