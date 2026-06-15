"""
Synthetic data generation for the HPV Screening Analytics Platform.

Generates realistic but entirely synthetic data. No results represent real
patients, populations, or healthcare systems. All names, addresses, and
identifiers are fabricated by the Faker library.

Run:
    python src/generate_data.py
    python src/generate_data.py --patients 1500 --seed 99
"""

from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import sqlite3

import numpy as np
import pandas as pd
from faker import Faker

# ─── Configuration ────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hpv_screening.db"

DEFAULT_SEED     = 42
N_PATIENTS       = 800
N_HOSPITALS      = 8
N_LOCATIONS      = 12
N_PROVIDERS      = 18
N_APPTS_PER_PAT  = (1, 3)   # uniform range

fake = Faker("en_US")

# ─── Reference data fixtures ──────────────────────────────────────────────────

INSURANCE_PLANS = [
    ("CommercialCare Premier",   "Private"),
    ("BlueCross Advantage",      "Private"),
    ("Medicaid Standard",        "Medicaid"),
    ("Medicaid Managed Care",    "Medicaid"),
    ("Medicare Part B",          "Medicare"),
    ("Self-Pay / Uninsured",     "Self-Pay"),
    ("ACA Marketplace Silver",   "ACA"),
    ("CHIP Children's Plan",     "CHIP"),
]

# No-show base rates by insurance type (signal baked into data generation)
INSURANCE_NOSHOW = {
    "Private":  0.10,
    "Medicaid": 0.18,
    "Medicare": 0.09,
    "Self-Pay": 0.26,
    "ACA":      0.14,
    "CHIP":     0.15,
}

HOSPITAL_TYPES = [
    ("University Medical Center",      "Academic"),
    ("Regional General Hospital",      "Community"),
    ("City Community Health Center",   "FQHC"),
    ("Women's Health Clinic",          "Specialty"),
    ("Northeast Family Practice",      "Private Practice"),
    ("Suburban Outpatient Center",     "Hospital Outpatient"),
    ("Riverside Health System",        "Community"),
    ("Metro Planned Parenthood",       "Reproductive Health"),
]

FACILITY_TYPES = [
    "Hospital Outpatient",
    "FQHC",
    "Private Practice",
    "Reproductive Health Clinic",
    "Community Health Center",
    "Academic Outpatient",
]

FACILITY_NOSHOW_OFFSET = {
    "Hospital Outpatient":      -0.02,
    "FQHC":                      0.06,
    "Private Practice":         -0.03,
    "Reproductive Health Clinic": 0.02,
    "Community Health Center":   0.04,
    "Academic Outpatient":      -0.01,
}

SPECIALTIES = [
    "OB/GYN",
    "Internal Medicine",
    "Family Medicine",
    "Primary Care / NP",
    "Gynecologic Oncology",
]

SCREENING_TYPES = [
    # (name, description, age_min, age_max, freq_months, modality)
    ("Pap Smear",       "Cervical cytology screening",              21, 65, 36,  "Cytology"),
    ("HPV DNA Test",    "High-risk HPV genotyping",                 25, 65, 60,  "Molecular"),
    ("Co-test",         "Pap smear + HPV DNA co-testing",           30, 65, 60,  "Co-test"),
    ("Colposcopy",      "Colposcopic evaluation after abnormal Pap",18, 70, None,"Colposcopy"),
    ("Cervical Biopsy", "Tissue biopsy for histological diagnosis", 18, 70, None,"Biopsy"),
]

ETHNICITIES = ["White", "Black", "Hispanic", "Asian", "Native American", "Other"]
ETHNICITY_WEIGHTS = [0.38, 0.22, 0.22, 0.10, 0.04, 0.04]

EDUCATION_LEVELS = ["Less than High School", "High School", "Some College",
                    "Associate", "Bachelor", "Graduate"]
EDUCATION_WEIGHTS = [0.12, 0.27, 0.20, 0.10, 0.20, 0.11]

STATES = ["PA", "NY", "NJ", "MD", "VA", "NC", "GA", "FL", "TX", "IL",
          "CA", "OH", "MI", "MA", "WA"]

RESULT_WEIGHTS = {
    "routine": {"Negative": 0.72, "Inconclusive": 0.09, "Positive": 0.10, "Abnormal": 0.09},
    "colpo":   {"Negative": 0.40, "Inconclusive": 0.10, "Positive": 0.25, "Abnormal": 0.25},
    "biopsy":  {"Negative": 0.30, "Inconclusive": 0.05, "Positive": 0.35, "Abnormal": 0.30},
}

FOLLOW_UP_ACTIONS = ["Repeat Pap in 6 months", "Colposcopy Referral",
                     "Cervical Biopsy", "Referred to Specialist",
                     "Watchful Waiting", "LEEP Procedure"]

FOLLOW_UP_OUTCOMES = ["Resolved", "Ongoing Monitoring",
                      "Referred to Specialist", "Lost to Follow-Up"]


# ─── Helper functions ─────────────────────────────────────────────────────────

def rand_date(start: date, end: date, rng: np.random.Generator) -> date:
    delta = (end - start).days
    return start + timedelta(days=int(rng.integers(0, max(delta, 1))))


def compute_noshow_prob(coverage: str, facility: str, age: int, education: str) -> float:
    base = INSURANCE_NOSHOW.get(coverage, 0.15)
    fac_offset = FACILITY_NOSHOW_OFFSET.get(facility, 0.0)

    # Younger patients (21-29) have higher no-show rate
    age_offset = 0.08 if age < 30 else (0.04 if age < 40 else 0.0)

    # Less education → slightly higher no-show rate
    edu_offset = 0.05 if education in ("Less than High School", "High School") else 0.0

    return min(max(base + fac_offset + age_offset + edu_offset, 0.04), 0.45)


# ─── Generation functions ─────────────────────────────────────────────────────

def build_insurance(rng) -> pd.DataFrame:
    rows = []
    for i, (plan, ctype) in enumerate(INSURANCE_PLANS, start=1):
        rows.append({
            "insurance_plan_id": i,
            "plan_name":         plan,
            "coverage_type":     ctype,
            "description":       f"{ctype} health insurance plan",
        })
    return pd.DataFrame(rows)


def build_hospitals(rng) -> pd.DataFrame:
    rows = []
    for i, (name, htype) in enumerate(HOSPITAL_TYPES, start=1):
        rows.append({
            "hospital_id":    i,
            "hospital_name":  name,
            "type":           htype,
            "phone_number":   fake.phone_number(),
            "email":          fake.company_email(),
        })
    return pd.DataFrame(rows)


def build_locations(hospitals_df: pd.DataFrame, rng) -> pd.DataFrame:
    n = N_LOCATIONS
    rows = []
    hosp_ids = hospitals_df["hospital_id"].tolist()
    for i in range(1, n + 1):
        h_id = int(rng.choice(hosp_ids))
        ftype = rng.choice(FACILITY_TYPES)
        rows.append({
            "location_id":   i,
            "hospital_id":   h_id,
            "address":       fake.street_address(),
            "city":          fake.city(),
            "state":         str(rng.choice(STATES)),
            "zip_code":      fake.zipcode(),
            "facility_type": ftype,
        })
    return pd.DataFrame(rows)


def build_providers(hospitals_df: pd.DataFrame, rng) -> pd.DataFrame:
    rows = []
    hosp_ids = hospitals_df["hospital_id"].tolist()
    for i in range(1, N_PROVIDERS + 1):
        rows.append({
            "provider_id":   i,
            "hospital_id":   int(rng.choice(hosp_ids)),
            "provider_name": fake.name(),
            "specialty":     str(rng.choice(SPECIALTIES)),
            "email":         fake.email(),
            "phone_number":  fake.phone_number(),
        })
    return pd.DataFrame(rows)


def build_screening_types() -> pd.DataFrame:
    rows = []
    for i, (name, desc, amin, amax, freq, mod) in enumerate(SCREENING_TYPES, start=1):
        rows.append({
            "screening_type_id":   i,
            "screening_name":      name,
            "description":         desc,
            "recommended_age_min": amin,
            "recommended_age_max": amax,
            "frequency_guideline": freq,
            "screening_modality":  mod,
        })
    return pd.DataFrame(rows)


def build_patients(insurance_df: pd.DataFrame, n: int, rng) -> pd.DataFrame:
    ins_ids = insurance_df["insurance_plan_id"].tolist()
    ins_types = insurance_df.set_index("insurance_plan_id")["coverage_type"].to_dict()

    rows = []
    for i in range(1, n + 1):
        # HPV screening is primarily female; ~78% F, 22% M in this dataset
        gender = "F" if rng.random() < 0.78 else "M"

        # Age: concentrate in 25-60 range (active screening window)
        age = int(np.clip(rng.normal(41, 12), 21, 72))
        dob = date.today() - timedelta(days=age * 365 + int(rng.integers(0, 365)))

        ethnicity  = str(rng.choice(ETHNICITIES, p=ETHNICITY_WEIGHTS))
        education  = str(rng.choice(EDUCATION_LEVELS, p=EDUCATION_WEIGHTS))
        ins_id     = int(rng.choice(ins_ids))

        rows.append({
            "patient_id":       i,
            "insurance_plan_id": ins_id,
            "first_name":       fake.first_name_female() if gender == "F" else fake.first_name_male(),
            "last_name":        fake.last_name(),
            "date_of_birth":    dob.isoformat(),
            "gender":           gender,
            "ethnicity":        ethnicity,
            "address":          fake.street_address(),
            "zip_code":         fake.zipcode(),
            "education_level":  education,
            "_coverage_type":   ins_types[ins_id],  # temp column for no-show calc
            "_age":             age,
            "_education":       education,
        })
    return pd.DataFrame(rows)


def build_appointments(
    patients_df:  pd.DataFrame,
    locations_df: pd.DataFrame,
    providers_df: pd.DataFrame,
    screening_df: pd.DataFrame,
    insurance_df: pd.DataFrame,
    rng,
) -> pd.DataFrame:

    loc_ids  = locations_df["location_id"].tolist()
    prov_ids = providers_df["provider_id"].tolist()
    screen_ids = screening_df["screening_type_id"].tolist()
    loc_ftype = locations_df.set_index("location_id")["facility_type"].to_dict()

    appt_start = date(2021, 1, 1)
    appt_end   = date(2025, 6, 1)

    rows = []
    appt_id = 1
    for _, pat in patients_df.iterrows():
        n_appts = int(rng.integers(N_APPTS_PER_PAT[0], N_APPTS_PER_PAT[1] + 1))
        for _ in range(n_appts):
            loc_id  = int(rng.choice(loc_ids))
            ftype   = loc_ftype[loc_id]
            coverage = str(pat["_coverage_type"])
            age      = int(pat["_age"])
            edu      = str(pat["_education"])

            p_noshow = compute_noshow_prob(coverage, ftype, age, edu)
            roll = rng.random()
            if roll < p_noshow:
                status = "No-Show"
            elif roll < p_noshow + 0.07:
                status = "Cancelled"
            elif roll < p_noshow + 0.08:
                status = "Scheduled"
            else:
                status = "Completed"

            sched_date = rand_date(appt_start, appt_end, rng)
            lead_days  = int(np.clip(rng.exponential(14), 1, 90))

            # Assign an age-appropriate screening type
            if age < 30:
                st_id = 1  # Pap Smear
            elif age < 40:
                st_id = int(rng.choice([1, 2, 3], p=[0.35, 0.30, 0.35]))
            else:
                st_id = int(rng.choice([1, 2, 3], p=[0.25, 0.25, 0.50]))

            rows.append({
                "appointment_id":    appt_id,
                "patient_id":        int(pat["patient_id"]),
                "insurance_plan_id": int(pat["insurance_plan_id"]),
                "location_id":       loc_id,
                "provider_id":       int(rng.choice(prov_ids)),
                "screening_type_id": st_id,
                "scheduled_date":    sched_date.isoformat(),
                "status":            status,
                "lead_time_days":    lead_days,
                "created_at":        (sched_date - timedelta(days=lead_days)).isoformat(),
                "updated_at":        sched_date.isoformat(),
            })
            appt_id += 1

    return pd.DataFrame(rows)


def build_screenings(appts_df: pd.DataFrame, rng) -> pd.DataFrame:
    completed = appts_df[appts_df["status"] == "Completed"].copy()
    rows = []
    scr_id = 1
    for _, appt in completed.iterrows():
        sched = date.fromisoformat(str(appt["scheduled_date"]))
        st_id = int(appt["screening_type_id"])

        if st_id <= 3:   # routine
            rw = RESULT_WEIGHTS["routine"]
        elif st_id == 4: # colposcopy
            rw = RESULT_WEIGHTS["colpo"]
        else:            # biopsy
            rw = RESULT_WEIGHTS["biopsy"]

        results = list(rw.keys())
        probs   = list(rw.values())
        result  = str(rng.choice(results, p=probs))

        rows.append({
            "screening_id":    scr_id,
            "appointment_id":  int(appt["appointment_id"]),
            "screening_date":  sched.isoformat(),
            "result":          result,
            "notes":           fake.sentence(nb_words=6),
            "created_at":      sched.isoformat(),
            "updated_at":      sched.isoformat(),
        })
        scr_id += 1

    return pd.DataFrame(rows)


def build_follow_ups(screenings_df: pd.DataFrame, rng) -> pd.DataFrame:
    abnormal = screenings_df[screenings_df["result"].isin(["Positive", "Abnormal"])].copy()
    rows = []
    fu_id = 1
    for _, scr in abnormal.iterrows():
        # ~68% of abnormal screenings receive follow-up
        if rng.random() > 0.68:
            continue

        scr_date = date.fromisoformat(str(scr["screening_date"]))
        # Follow-up typically occurs 14–90 days after abnormal result
        fu_days = int(np.clip(rng.normal(35, 20), 7, 120))
        fu_date = scr_date + timedelta(days=fu_days)

        action  = str(rng.choice(FOLLOW_UP_ACTIONS))
        outcome = str(rng.choice(FOLLOW_UP_OUTCOMES,
                                 p=[0.45, 0.30, 0.15, 0.10]))
        rows.append({
            "follow_up_id":  fu_id,
            "screening_id":  int(scr["screening_id"]),
            "follow_up_date": fu_date.isoformat(),
            "action_taken":  action,
            "outcome":       outcome,
            "notes":         fake.sentence(nb_words=8),
            "created_at":    fu_date.isoformat(),
            "updated_at":    fu_date.isoformat(),
        })
        fu_id += 1

    return pd.DataFrame(rows)


# ─── Database creation ────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS insurance_type (
    insurance_plan_id INTEGER PRIMARY KEY,
    plan_name         TEXT NOT NULL,
    coverage_type     TEXT NOT NULL,
    description       TEXT
);

CREATE TABLE IF NOT EXISTS hospital (
    hospital_id   INTEGER PRIMARY KEY,
    hospital_name TEXT NOT NULL,
    type          TEXT,
    phone_number  TEXT,
    email         TEXT
);

CREATE TABLE IF NOT EXISTS screening_type (
    screening_type_id   INTEGER PRIMARY KEY,
    screening_name      TEXT NOT NULL,
    description         TEXT,
    recommended_age_min INTEGER,
    recommended_age_max INTEGER,
    frequency_guideline INTEGER,
    screening_modality  TEXT
);

CREATE TABLE IF NOT EXISTS patient (
    patient_id        INTEGER PRIMARY KEY,
    insurance_plan_id INTEGER NOT NULL REFERENCES insurance_type(insurance_plan_id),
    first_name        TEXT,
    last_name         TEXT,
    date_of_birth     TEXT,
    gender            TEXT,
    ethnicity         TEXT,
    address           TEXT,
    zip_code          TEXT,
    education_level   TEXT
);

CREATE TABLE IF NOT EXISTS location (
    location_id   INTEGER PRIMARY KEY,
    hospital_id   INTEGER NOT NULL REFERENCES hospital(hospital_id),
    address       TEXT,
    city          TEXT,
    state         TEXT,
    zip_code      TEXT,
    facility_type TEXT
);

CREATE TABLE IF NOT EXISTS provider (
    provider_id   INTEGER PRIMARY KEY,
    hospital_id   INTEGER NOT NULL REFERENCES hospital(hospital_id),
    provider_name TEXT,
    specialty     TEXT,
    email         TEXT,
    phone_number  TEXT
);

CREATE TABLE IF NOT EXISTS appointment (
    appointment_id    INTEGER PRIMARY KEY,
    patient_id        INTEGER NOT NULL REFERENCES patient(patient_id),
    insurance_plan_id INTEGER NOT NULL REFERENCES insurance_type(insurance_plan_id),
    location_id       INTEGER NOT NULL REFERENCES location(location_id),
    provider_id       INTEGER NOT NULL REFERENCES provider(provider_id),
    screening_type_id INTEGER NOT NULL REFERENCES screening_type(screening_type_id),
    scheduled_date    TEXT,
    status            TEXT NOT NULL DEFAULT 'Scheduled',
    lead_time_days    INTEGER,
    created_at        TEXT,
    updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS screening (
    screening_id   INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL UNIQUE REFERENCES appointment(appointment_id),
    screening_date TEXT,
    result         TEXT,
    notes          TEXT,
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS follow_up (
    follow_up_id  INTEGER PRIMARY KEY,
    screening_id  INTEGER NOT NULL UNIQUE REFERENCES screening(screening_id),
    follow_up_date TEXT,
    action_taken  TEXT,
    outcome       TEXT,
    notes         TEXT,
    created_at    TEXT,
    updated_at    TEXT
);
"""


def write_to_db(db_path: Path, tables: dict[str, pd.DataFrame]) -> None:
    import sqlite3
    db_file = str(db_path)

    # Drop temp columns before loading
    pat = tables["patient"].drop(
        columns=[c for c in tables["patient"].columns if c.startswith("_")],
        errors="ignore",
    )

    order = [
        ("insurance_type", tables["insurance_type"]),
        ("hospital",       tables["hospital"]),
        ("screening_type", tables["screening_type"]),
        ("patient",        pat),
        ("location",       tables["location"]),
        ("provider",       tables["provider"]),
        ("appointment",    tables["appointment"]),
        ("screening",      tables["screening"]),
        ("follow_up",      tables["follow_up"]),
    ]

    with sqlite3.connect(db_file) as con:
        for stmt in DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                try:
                    con.execute(s)
                except sqlite3.OperationalError:
                    pass
        con.commit()

        for tname, df in order:
            df.to_sql(tname, con, if_exists="replace", index=False)
            print(f"  Loaded {len(df):>5} rows -> {tname}")


# ─── Entry point ──────────────────────────────────────────────────────────────

def generate(n_patients: int = N_PATIENTS, seed: int = DEFAULT_SEED) -> None:
    print(f"\nGenerating synthetic HPV screening data (n={n_patients}, seed={seed})")
    print("NOTE: All data is synthetic. No results represent real populations.\n")

    Faker.seed(seed)
    rng = np.random.default_rng(seed)
    random.seed(seed)

    insurance  = build_insurance(rng)
    hospitals  = build_hospitals(rng)
    scr_types  = build_screening_types()
    patients   = build_patients(insurance, n_patients, rng)
    locations  = build_locations(hospitals, rng)
    providers  = build_providers(hospitals, rng)
    appts      = build_appointments(patients, locations, providers, scr_types, insurance, rng)
    screenings = build_screenings(appts, rng)
    follow_ups = build_follow_ups(screenings, rng)

    tables = {
        "insurance_type": insurance,
        "hospital":       hospitals,
        "screening_type": scr_types,
        "patient":        patients,
        "location":       locations,
        "provider":       providers,
        "appointment":    appts,
        "screening":      screenings,
        "follow_up":      follow_ups,
    }

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_to_db(DB_PATH, tables)

    print(f"\nDatabase written to: {DB_PATH}")
    print("\nSummary:")
    print(f"  Patients:     {len(patients)}")
    print(f"  Appointments: {len(appts)}")
    print(f"  Screenings:   {len(screenings)}")
    print(f"  Follow-ups:   {len(follow_ups)}")
    print(f"  No-show rate: {(appts['status']=='No-Show').mean():.1%}")
    print(f"  Abnormal rate:{(screenings['result'].isin(['Positive','Abnormal'])).mean():.1%}")
    print(f"  Follow-up completion (of abnormal): "
          f"{len(follow_ups)/max((screenings['result'].isin(['Positive','Abnormal'])).sum(),1):.1%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--patients", type=int, default=N_PATIENTS)
    parser.add_argument("--seed",     type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    generate(n_patients=args.patients, seed=args.seed)
