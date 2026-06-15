"""
Data validation and cleaning utilities.

Validates the SQLite database produced by generate_data.py and produces
a quality report. Can also be applied to externally sourced data before
loading it into the analytics pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hpv_screening.db"

VALID_STATUSES  = {"Completed", "No-Show", "Cancelled", "Scheduled"}
VALID_GENDERS   = {"F", "M", "O"}
VALID_RESULTS   = {"Negative", "Positive", "Inconclusive", "Abnormal"}


def load_tables(db_path: Path = DB_PATH) -> dict[str, pd.DataFrame]:
    engine = create_engine(f"sqlite:///{db_path}")
    tables = ["insurance_type", "hospital", "screening_type", "patient",
              "location", "provider", "appointment", "screening", "follow_up"]
    return {t: pd.read_sql_table(t, engine) for t in tables}


# ─── Row-level validators ─────────────────────────────────────────────────────

def validate_patients(df: pd.DataFrame) -> pd.DataFrame:
    issues = []

    null_dob = df["date_of_birth"].isna().sum()
    if null_dob:
        issues.append(f"  {null_dob} patients missing date_of_birth")

    invalid_gender = ~df["gender"].isin(VALID_GENDERS) & df["gender"].notna()
    if invalid_gender.any():
        issues.append(f"  {invalid_gender.sum()} patients with unexpected gender value")

    dob_series = pd.to_datetime(df["date_of_birth"], errors="coerce")
    age = (pd.Timestamp.today() - dob_series).dt.days / 365.25
    too_young = (age < 18).sum()
    too_old   = (age > 100).sum()
    if too_young:
        issues.append(f"  {too_young} patients younger than 18")
    if too_old:
        issues.append(f"  {too_old} patients older than 100")

    return _report("patient", issues, len(df))


def validate_appointments(df: pd.DataFrame) -> pd.DataFrame:
    issues = []

    invalid_status = ~df["status"].isin(VALID_STATUSES)
    if invalid_status.any():
        issues.append(f"  {invalid_status.sum()} appointments with unknown status")

    null_date = df["scheduled_date"].isna().sum()
    if null_date:
        issues.append(f"  {null_date} appointments missing scheduled_date")

    neg_lead = (df["lead_time_days"].fillna(0) < 0).sum()
    if neg_lead:
        issues.append(f"  {neg_lead} appointments with negative lead_time_days")

    return _report("appointment", issues, len(df))


def validate_screenings(df: pd.DataFrame) -> pd.DataFrame:
    issues = []

    invalid_result = ~df["result"].isin(VALID_RESULTS) & df["result"].notna()
    if invalid_result.any():
        issues.append(f"  {invalid_result.sum()} screenings with unexpected result value")

    null_date = df["screening_date"].isna().sum()
    if null_date:
        issues.append(f"  {null_date} screenings missing screening_date")

    dups = df["appointment_id"].duplicated().sum()
    if dups:
        issues.append(f"  {dups} duplicate appointment_id in screening table")

    return _report("screening", issues, len(df))


def validate_follow_ups(df: pd.DataFrame) -> pd.DataFrame:
    issues = []

    dups = df["screening_id"].duplicated().sum()
    if dups:
        issues.append(f"  {dups} duplicate screening_id in follow_up table")

    null_date = df["follow_up_date"].isna().sum()
    if null_date:
        issues.append(f"  {null_date} follow-ups missing follow_up_date")

    return _report("follow_up", issues, len(df))


def _report(table: str, issues: list[str], n_rows: int) -> dict:
    status = "PASS" if not issues else "WARN"
    return {"table": table, "n_rows": n_rows, "status": status, "issues": issues}


# ─── Summary statistics ───────────────────────────────────────────────────────

def missingness_report(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for tname, df in tables.items():
        for col in df.columns:
            pct = df[col].isna().mean() * 100
            if pct > 0:
                rows.append({"table": tname, "column": col, "pct_missing": round(pct, 1)})
    return pd.DataFrame(rows).sort_values("pct_missing", ascending=False)


def referential_integrity_check(tables: dict[str, pd.DataFrame]) -> list[str]:
    issues = []

    appt_patient_ids = set(tables["appointment"]["patient_id"])
    patient_ids      = set(tables["patient"]["patient_id"])
    orphan_patients  = appt_patient_ids - patient_ids
    if orphan_patients:
        issues.append(f"  {len(orphan_patients)} appointment rows reference unknown patient_id")

    scr_appt_ids  = set(tables["screening"]["appointment_id"])
    appt_ids      = set(tables["appointment"]["appointment_id"])
    orphan_appts  = scr_appt_ids - appt_ids
    if orphan_appts:
        issues.append(f"  {len(orphan_appts)} screening rows reference unknown appointment_id")

    fu_scr_ids   = set(tables["follow_up"]["screening_id"])
    scr_ids      = set(tables["screening"]["screening_id"])
    orphan_scrs  = fu_scr_ids - scr_ids
    if orphan_scrs:
        issues.append(f"  {len(orphan_scrs)} follow_up rows reference unknown screening_id")

    return issues


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_qa(db_path: Path = DB_PATH) -> None:
    print(f"\nRunning data quality checks on: {db_path}\n")
    tables = load_tables(db_path)

    reports = [
        validate_patients(tables["patient"]),
        validate_appointments(tables["appointment"]),
        validate_screenings(tables["screening"]),
        validate_follow_ups(tables["follow_up"]),
    ]

    print("─── Per-table validation ───────────────────────────────")
    for r in reports:
        icon = "✓" if r["status"] == "PASS" else "⚠"
        print(f"  {icon} {r['table']:<20} {r['n_rows']:>5} rows  [{r['status']}]")
        for issue in r["issues"]:
            print(issue)

    print("\n─── Referential integrity ──────────────────────────────")
    ri_issues = referential_integrity_check(tables)
    if ri_issues:
        for iss in ri_issues:
            print(iss)
    else:
        print("  ✓ All foreign key references resolved")

    miss = missingness_report(tables)
    if not miss.empty:
        print("\n─── Missingness (only columns with >0% missing) ───────")
        print(miss.to_string(index=False))
    else:
        print("\n─── Missingness ────────────────────────────────────────")
        print("  ✓ No missing values detected")

    print("\nQA complete.")


if __name__ == "__main__":
    run_qa()
