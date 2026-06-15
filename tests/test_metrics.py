"""
Unit tests for src/metrics.py.
Run: pytest tests/
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.metrics import (
    summary_kpis, monthly_volume, no_show_by_group,
    screening_rate_by_education, provider_workload,
    appointments_by_state,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_dfs() -> dict:
    insurance = pd.DataFrame([
        {"insurance_plan_id": 1, "plan_name": "Plan A", "coverage_type": "Private"},
        {"insurance_plan_id": 2, "plan_name": "Plan B", "coverage_type": "Medicaid"},
        {"insurance_plan_id": 3, "plan_name": "Self",   "coverage_type": "Self-Pay"},
    ])
    patient = pd.DataFrame({
        "patient_id":       [1, 2, 3, 4],
        "insurance_plan_id":[1, 2, 3, 1],
        "date_of_birth":    ["1980-01-01", "1990-06-15", "1975-03-22", "2000-11-01"],
        "gender":           ["F", "F", "M", "F"],
        "ethnicity":        ["White", "Black", "Hispanic", "Asian"],
        "education_level":  ["Bachelor", "High School", "Graduate", "Some College"],
        "zip_code":         ["19103", "19104", "19105", "19106"],
    })
    hospital = pd.DataFrame([
        {"hospital_id": 1, "hospital_name": "City Hospital", "type": "Community"},
    ])
    location = pd.DataFrame([
        {"location_id": 1, "hospital_id": 1, "city": "Philly",
         "state": "PA", "zip_code": "19103", "facility_type": "Hospital Outpatient"},
        {"location_id": 2, "hospital_id": 1, "city": "Philly",
         "state": "PA", "zip_code": "19104", "facility_type": "FQHC"},
    ])
    provider = pd.DataFrame([
        {"provider_id": 1, "hospital_id": 1, "provider_name": "Dr. A", "specialty": "OB/GYN"},
        {"provider_id": 2, "hospital_id": 1, "provider_name": "Dr. B", "specialty": "Family Medicine"},
    ])
    screening_type = pd.DataFrame([
        {"screening_type_id": 1, "screening_name": "Pap Smear",
         "screening_modality": "Cytology"},
    ])
    appointment = pd.DataFrame({
        "appointment_id":    [1, 2, 3, 4, 5],
        "patient_id":        [1, 2, 3, 4, 1],
        "insurance_plan_id": [1, 2, 3, 1, 1],
        "location_id":       [1, 1, 2, 2, 1],
        "provider_id":       [1, 1, 2, 2, 1],
        "screening_type_id": [1, 1, 1, 1, 1],
        "scheduled_date":    ["2023-01-15", "2023-02-20", "2023-01-10",
                              "2023-03-05", "2023-03-15"],
        "status":            ["Completed", "No-Show", "Completed", "Cancelled", "Completed"],
        "lead_time_days":    [7, 14, 5, 21, 10],
        "created_at":        ["2023-01-08"] * 5,
        "updated_at":        ["2023-01-15"] * 5,
    })
    screening = pd.DataFrame({
        "screening_id":   [1, 2, 3],
        "appointment_id": [1, 3, 5],
        "screening_date": ["2023-01-15", "2023-01-10", "2023-03-15"],
        "result":         ["Negative", "Positive", "Abnormal"],
        "notes":          ["OK", "Follow-up needed", "Review required"],
        "created_at":     ["2023-01-15"] * 3,
        "updated_at":     ["2023-01-15"] * 3,
    })
    follow_up = pd.DataFrame({
        "follow_up_id":   [1],
        "screening_id":   [2],
        "follow_up_date": ["2023-02-15"],
        "action_taken":   ["Colposcopy Referral"],
        "outcome":        ["Resolved"],
        "notes":          ["Completed"],
        "created_at":     ["2023-02-15"],
        "updated_at":     ["2023-02-15"],
    })

    for df in [appointment]:
        df["scheduled_date"] = pd.to_datetime(df["scheduled_date"])
    for df in [screening]:
        df["screening_date"] = pd.to_datetime(df["screening_date"])
    patient["date_of_birth"] = pd.to_datetime(patient["date_of_birth"])
    follow_up["follow_up_date"] = pd.to_datetime(follow_up["follow_up_date"])

    return {
        "insurance_type": insurance,
        "patient":        patient,
        "hospital":       hospital,
        "location":       location,
        "provider":       provider,
        "screening_type": screening_type,
        "appointment":    appointment,
        "screening":      screening,
        "follow_up":      follow_up,
    }


@pytest.fixture
def dfs():
    return _make_dfs()


@pytest.fixture
def master(dfs):
    from src.metrics import build_master
    return build_master(dfs)


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestSummaryKPIs:
    def test_patient_count(self, dfs):
        kpis = summary_kpis(dfs)
        assert kpis["total_patients"] == 4

    def test_appointment_count(self, dfs):
        kpis = summary_kpis(dfs)
        assert kpis["total_appointments"] == 5

    def test_no_show_rate(self, dfs):
        kpis = summary_kpis(dfs)
        # 1 no-show out of 5 appointments
        assert abs(kpis["no_show_rate"] - 0.2) < 1e-9

    def test_abnormal_rate(self, dfs):
        kpis = summary_kpis(dfs)
        # 2 abnormal out of 3 screenings
        assert abs(kpis["abnormal_rate"] - 2 / 3) < 1e-9

    def test_follow_up_completion(self, dfs):
        kpis = summary_kpis(dfs)
        # 1 follow-up of 2 abnormal screenings = 0.5
        assert abs(kpis["follow_up_completion"] - 0.5) < 1e-9

    def test_screening_rate_lte_one(self, dfs):
        kpis = summary_kpis(dfs)
        assert 0 <= kpis["screening_rate"] <= 1


class TestBuildMaster:
    def test_shape(self, master):
        assert len(master) == 5

    def test_no_show_flag(self, master):
        assert master["no_show"].sum() == 1

    def test_age_computed(self, master):
        assert master["age"].notna().any()
        assert (master["age"] >= 0).all()

    def test_age_group_present(self, master):
        assert "age_group" in master.columns

    def test_year_month_format(self, master):
        # all should look like YYYY-MM
        for ym in master["year_month"].dropna():
            assert len(str(ym)) == 7, f"Unexpected year_month format: {ym}"


class TestNoShowByGroup:
    def test_insurance_groups(self, master):
        df = no_show_by_group(master, "coverage_type")
        assert "coverage_type" in df.columns
        assert "no_show_rate" in df.columns
        assert (df["no_show_rate"] >= 0).all()
        assert (df["no_show_rate"] <= 1).all()

    def test_sum_of_totals_equals_appts(self, master, dfs):
        df = no_show_by_group(master, "coverage_type")
        assert df["total"].sum() == len(dfs["appointment"])


class TestScreeningRateByEducation:
    def test_returns_dataframe(self, master):
        df = screening_rate_by_education(master)
        assert isinstance(df, pd.DataFrame)

    def test_completion_rate_bounded(self, master):
        df = screening_rate_by_education(master)
        assert (df["completion_rate"] >= 0).all()
        assert (df["completion_rate"] <= 1).all()


class TestProviderWorkload:
    def test_provider_count(self, master, dfs):
        df = provider_workload(master)
        n_providers = dfs["provider"]["provider_id"].nunique()
        assert len(df) == n_providers

    def test_no_show_rate_present(self, master):
        df = provider_workload(master)
        assert "no_show_rate" in df.columns

    def test_no_negative_counts(self, master):
        df = provider_workload(master)
        assert (df["total_appointments"] >= 0).all()
        assert (df["no_shows"] >= 0).all()


class TestAppointmentsByState:
    def test_columns_present(self, master):
        df = appointments_by_state(master)
        for col in ["state", "appointments", "no_show_rate"]:
            assert col in df.columns

    def test_only_pa_present(self, master):
        df = appointments_by_state(master)
        assert set(df["state"]) == {"PA"}
