# Methodology — HPV Screening Analytics Platform

## Overview

This platform is a portfolio project demonstrating healthcare analytics
engineering using a synthetic relational database modeled after real-world
HPV cervical cancer screening workflows. All data is generated programmatically;
no real patient or provider data is used.

---

## Data Generation

### Schema design

The relational schema follows a normalized, star-schema-like structure centered
on the `appointment` table. Reference tables (insurance types, hospitals,
screening types) are populated with realistic but synthetic fixtures.
Transactional tables (appointments, screenings, follow-ups) are generated
with embedded statistical signal to produce analytically meaningful patterns.

### Synthetic signal embedding

The following real-world patterns are approximated in data generation to
produce interpretable model results:

| Factor | Embedded effect on no-show probability |
|--------|---------------------------------------|
| Self-Pay insurance | Base no-show rate ≈ 26% |
| Medicaid | Base no-show rate ≈ 18% |
| Private insurance | Base no-show rate ≈ 10% |
| Age < 30 | +8 percentage points (pp) |
| Age 30–39 | +4 pp |
| Less than HS / HS education | +5 pp |
| FQHC facility | +6 pp |
| Community Health Center | +4 pp |
| Hospital Outpatient | −2 pp |
| Private Practice | −3 pp |

These offsets are additive and clamped to [4%, 45%]. They are intended solely
to produce a learnable signal for the model demonstration, not to represent
empirically validated risk estimates.

### Data volume defaults

| Table | Default N |
|-------|-----------|
| Patients | 800 |
| Hospitals | 8 |
| Locations | 12 |
| Providers | 18 |
| Insurance plans | 8 |
| Screening types | 5 |
| Appointments | ~1,200–1,700 (1–3 per patient) |
| Screenings | ~75% of appointments (Completed only) |
| Follow-ups | ~68% of Positive/Abnormal screenings |

Run `python src/generate_data.py --patients 1500` to scale up.

---

## KPI Definitions

| KPI | Formula |
|-----|---------|
| No-show rate | `n(No-Show) / n(All appointments)` |
| Screening completion rate | `n(Completed) / n(All appointments)` |
| Abnormal screening rate | `n(result ∈ {Positive, Abnormal}) / n(All screenings)` |
| Follow-up completion rate | `n(follow-up records) / n(abnormal screenings)` |
| Time to follow-up | `follow_up_date − screening_date` (days) |

---

## No-Show Prediction Model

### Objective

Binary classification: will a patient show up (`status == 'Completed'`) or not
(`status == 'No-Show'`)? Cancelled and Scheduled appointments are excluded from
the modeling dataset.

### Features

**Numeric:**
- `age` — patient age at time of appointment
- `lead_time_days` — days between booking and appointment

**Categorical (one-hot encoded):**
- `gender`
- `ethnicity`
- `education_level`
- `coverage_type` (insurance category)
- `facility_type`
- `specialty` (provider specialty)

### Models

| Model | Purpose |
|-------|---------|
| Logistic Regression | Primary — interpretable coefficients as feature importance |
| Decision Tree (depth ≤ 4) | Secondary — visual rule extraction |

Both models use `class_weight='balanced'` to account for class imbalance
(no-shows are the minority class at ~15–18%).

### Evaluation

- 5-fold stratified cross-validation (AUC-ROC)
- Confusion matrix on the full training set (for dashboard display only)
- Average precision score

**Important caveat:** The model is trained and evaluated on the same synthetic
dataset. Cross-validation AUC is the more honest performance estimate. In a
real deployment, a held-out test set from real clinical data would be required.

---

## Analytical Views

Five SQL views are defined in `database/views.sql` to support common query
patterns without requiring complex joins in application code:

| View | Description |
|------|-------------|
| `v_patient_insurance` | Demographics + insurance type |
| `v_appointment_location` | Appointment + facility geography |
| `v_screening_detail` | Screening results + screening type + patient age at screening |
| `v_provider_activity` | Provider-level workload and abnormal/no-show rates |
| `v_appointment_overview` | Full flat view for reporting |

---

## Limitations

See `docs/limitations.md` for a complete discussion.
