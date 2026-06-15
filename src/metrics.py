"""
KPI and metric calculation functions for the HPV Screening Analytics Platform.

All metrics operate on pandas DataFrames loaded from the SQLite database.
Functions return DataFrames or scalar values suitable for display in Streamlit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hpv_screening.db"


# ─── Data loader ──────────────────────────────────────────────────────────────

def load_all(db_path: Path = DB_PATH) -> dict[str, pd.DataFrame]:
    """Load all tables and return as a dict of DataFrames."""
    import sqlite3
    tables = ["insurance_type", "hospital", "screening_type", "patient",
              "location", "provider", "appointment", "screening", "follow_up"]
    with sqlite3.connect(db_path) as con:
        dfs = {t: pd.read_sql(f"SELECT * FROM {t}", con) for t in tables}

    # Parse dates
    dfs["patient"]["date_of_birth"]        = pd.to_datetime(dfs["patient"]["date_of_birth"], errors="coerce")
    dfs["appointment"]["scheduled_date"]   = pd.to_datetime(dfs["appointment"]["scheduled_date"], errors="coerce")
    dfs["screening"]["screening_date"]     = pd.to_datetime(dfs["screening"]["screening_date"], errors="coerce")
    dfs["follow_up"]["follow_up_date"]     = pd.to_datetime(dfs["follow_up"]["follow_up_date"], errors="coerce")

    return dfs


def build_master(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Flat wide table joining all appointment-level data for analysis."""
    appt = dfs["appointment"].copy()
    pat  = dfs["patient"][["patient_id", "date_of_birth", "gender", "ethnicity",
                            "education_level", "zip_code"]].copy()
    ins  = dfs["insurance_type"][["insurance_plan_id", "plan_name", "coverage_type"]].copy()
    loc  = dfs["location"][["location_id", "city", "state", "facility_type"]].copy()
    prov = dfs["provider"][["provider_id", "provider_name", "specialty"]].copy()
    scr  = dfs["screening_type"][["screening_type_id", "screening_name", "screening_modality"]].copy()
    scn  = dfs["screening"][["appointment_id", "result", "screening_date"]].copy()
    fu   = dfs["follow_up"][["screening_id", "follow_up_date", "action_taken", "outcome"]].copy()
    scn_full = scn.merge(
        dfs["screening"][["screening_id", "appointment_id"]].rename(columns={"appointment_id": "appt_id_ref"}),
        left_on="appointment_id", right_on="appt_id_ref", how="left"
    )

    master = (appt
              .merge(pat,  on="patient_id",        how="left")
              .merge(ins,  on="insurance_plan_id",  how="left")
              .merge(loc,  on="location_id",        how="left")
              .merge(prov, on="provider_id",        how="left")
              .merge(scr,  on="screening_type_id",  how="left")
              .merge(scn,  on="appointment_id",     how="left"))

    master["age"] = ((master["scheduled_date"] - master["date_of_birth"])
                     .dt.days / 365.25).round(1)
    master["age_group"] = pd.cut(
        master["age"],
        bins=[0, 29, 39, 49, 64, 200],
        labels=["21–29", "30–39", "40–49", "50–64", "65+"],
    )
    master["year_month"] = master["scheduled_date"].dt.to_period("M").astype(str)
    master["year"]       = master["scheduled_date"].dt.year
    master["no_show"]    = (master["status"] == "No-Show").astype(int)
    master["completed"]  = (master["status"] == "Completed").astype(int)
    master["abnormal"]   = master["result"].isin(["Positive", "Abnormal"]).astype(int)

    return master


# ─── Top-level KPIs ───────────────────────────────────────────────────────────

def summary_kpis(dfs: dict[str, pd.DataFrame]) -> dict:
    appt = dfs["appointment"]
    scr  = dfs["screening"]
    fu   = dfs["follow_up"]
    pat  = dfs["patient"]

    total_patients  = int(pat["patient_id"].nunique())
    total_appts     = int(len(appt))
    completed_appts = int((appt["status"] == "Completed").sum())
    no_show_rate    = float((appt["status"] == "No-Show").mean())
    total_screenings = int(len(scr))
    abnormal_count  = int(scr["result"].isin(["Positive", "Abnormal"]).sum())
    abnormal_rate   = float(abnormal_count / max(total_screenings, 1))
    fu_completion   = float(len(fu) / max(abnormal_count, 1))

    return {
        "total_patients":    total_patients,
        "total_appointments": total_appts,
        "completed_appts":   completed_appts,
        "screening_rate":    completed_appts / max(total_appts, 1),
        "no_show_rate":      no_show_rate,
        "total_screenings":  total_screenings,
        "abnormal_rate":     abnormal_rate,
        "follow_up_completion": fu_completion,
    }


# ─── Time-series metrics ──────────────────────────────────────────────────────

def monthly_volume(master: pd.DataFrame) -> pd.DataFrame:
    return (master
            .groupby("year_month")
            .agg(
                appointments=("appointment_id", "count"),
                completed=("completed", "sum"),
                no_shows=("no_show", "sum"),
            )
            .reset_index()
            .sort_values("year_month"))


# ─── Demographic metrics ──────────────────────────────────────────────────────

def no_show_by_group(master: pd.DataFrame, group_col: str) -> pd.DataFrame:
    g = master.groupby(group_col, observed=True)
    return (g.agg(
                total=("appointment_id", "count"),
                no_shows=("no_show", "sum"),
            )
            .assign(no_show_rate=lambda d: d["no_shows"] / d["total"])
            .reset_index()
            .sort_values("no_show_rate", ascending=False))


def screening_rate_by_education(master: pd.DataFrame) -> pd.DataFrame:
    g = master.groupby("education_level", observed=True)
    return (g.agg(
                total_appts=("appointment_id", "count"),
                completed=("completed", "sum"),
            )
            .assign(completion_rate=lambda d: d["completed"] / d["total_appts"])
            .reset_index()
            .sort_values("completion_rate", ascending=False))


def age_distribution(master: pd.DataFrame) -> pd.DataFrame:
    return (master[master["completed"] == 1]
            .groupby("age_group", observed=True)
            .size()
            .reset_index(name="screenings"))


# ─── Provider metrics ─────────────────────────────────────────────────────────

def provider_workload(master: pd.DataFrame) -> pd.DataFrame:
    return (master
            .groupby(["provider_name", "specialty"], observed=True)
            .agg(
                total_appointments=("appointment_id", "count"),
                completed=("completed", "sum"),
                no_shows=("no_show", "sum"),
                abnormal_screenings=("abnormal", "sum"),
            )
            .assign(
                no_show_rate=lambda d: d["no_shows"] / d["total_appointments"],
                abnormal_rate=lambda d: d["abnormal_screenings"] / d["completed"].replace(0, pd.NA),
            )
            .reset_index()
            .sort_values("total_appointments", ascending=False))


def no_show_by_specialty(master: pd.DataFrame) -> pd.DataFrame:
    return no_show_by_group(master, "specialty")


# ─── Geographic metrics ───────────────────────────────────────────────────────

def appointments_by_state(master: pd.DataFrame) -> pd.DataFrame:
    return (master
            .groupby("state", observed=True)
            .agg(
                appointments=("appointment_id", "count"),
                patients=("patient_id", "nunique"),
                no_show_rate=("no_show", "mean"),
            )
            .reset_index()
            .sort_values("appointments", ascending=False))


def facility_type_distribution(master: pd.DataFrame) -> pd.DataFrame:
    return (master
            .groupby("facility_type", observed=True)
            .agg(
                appointments=("appointment_id", "count"),
                no_show_rate=("no_show", "mean"),
            )
            .reset_index())


# ─── Follow-up metrics ────────────────────────────────────────────────────────

def time_to_follow_up(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    scr = dfs["screening"][["screening_id", "screening_date", "result"]].copy()
    fu  = dfs["follow_up"][["screening_id", "follow_up_date"]].copy()
    merged = scr.merge(fu, on="screening_id", how="inner")
    merged["days_to_follow_up"] = (
        merged["follow_up_date"] - merged["screening_date"]
    ).dt.days
    return merged[merged["result"].isin(["Positive", "Abnormal"])].copy()


def follow_up_outcomes(dfs: pd.DataFrame) -> pd.DataFrame:
    return (dfs["follow_up"]
            .groupby("outcome")
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False))


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dfs = load_all()
    kpis = summary_kpis(dfs)
    print("\n── Summary KPIs ────────────────────────────────────────")
    for k, v in kpis.items():
        if isinstance(v, float):
            print(f"  {k:<30} {v:.1%}")
        else:
            print(f"  {k:<30} {v:,}")

    master = build_master(dfs)
    print("\n── No-show by insurance type ───────────────────────────")
    print(no_show_by_group(master, "coverage_type").to_string(index=False))

    print("\n── Provider workload (top 5) ───────────────────────────")
    print(provider_workload(master).head(5).to_string(index=False))
