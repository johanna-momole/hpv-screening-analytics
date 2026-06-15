# HPV Screening Access and Follow-Up Analytics Platform

A production-style healthcare analytics portfolio project demonstrating
data engineering, KPI analysis, predictive modeling, and interactive
visualization for HPV cervical cancer screening workflows.

> **All data is synthetic.** No patient records, clinical outcomes, or
> provider data in this project are real. Results must not be used for
> clinical decisions, policy, or public health reporting.

---

## Features

| Layer | Description |
|-------|-------------|
| **Relational schema** | Normalized MySQL/SQLite schema (patients, insurance, hospitals, locations, providers, screening types, appointments, screenings, follow-ups) |
| **Synthetic data generator** | ~800 patients, ~1,400 appointments, realistic no-show and abnormal result distributions |
| **Data validation** | Referential integrity checks, missingness reports, per-table QA |
| **KPI engine** | No-show rate, screening completion, abnormal rate, follow-up completion, time-to-follow-up |
| **Predictive model** | Logistic regression (primary) + decision tree (secondary) for no-show risk, with cross-validated AUC |
| **Dashboard** | 5-page Streamlit app — Overview, Demographics, Providers, Geography, No-Show Predictor |
| **Docker** | Single-command container deployment |

---

## Quick Start

### Local (recommended for development)

```bash
# 1. Clone the repo
git clone https://github.com/johanna-momole/hpv-screening-analytics.git
cd hpv-screening-analytics

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate synthetic data (creates data/hpv_screening.db)
python src/generate_data.py

# 5. Run data quality checks (optional)
python src/clean_data.py

# 6. Launch the dashboard
streamlit run app/streamlit_app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

### Docker

```bash
docker-compose up --build
```

---

## Project Structure

```
hpv-screening-analytics/
├── data/
│   ├── raw/                  # place external source files here
│   └── processed/            # intermediate outputs
├── database/
│   ├── schema.sql            # MySQL 8.0 DDL (production)
│   ├── views.sql             # 5 analytical views
│   └── analytical_queries.sql # 12 business-level queries
├── src/
│   ├── generate_data.py      # synthetic data generation → SQLite
│   ├── clean_data.py         # data validation and QA
│   ├── metrics.py            # KPI functions
│   └── modeling.py           # no-show prediction model
├── app/
│   └── streamlit_app.py      # 5-page interactive dashboard
├── notebooks/
│   ├── exploratory_analysis.ipynb
│   └── no_show_model.ipynb
├── tests/
│   └── test_metrics.py       # pytest unit tests
├── docs/
│   ├── data_dictionary.md
│   ├── methodology.md
│   └── limitations.md
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Dashboard Pages

| Page | Key Content |
|------|-------------|
| **Overview** | Total patients/appointments, monthly volume trend, status and result distributions |
| **Demographics** | Age/gender histogram, ethnicity breakdown, no-show rate by insurance and ethnicity, completion by education |
| **Providers** | Workload bar chart, no-show scatter, specialty-level abnormal and no-show rates, provider scorecard table |
| **Geography** | US choropleth maps (appointment volume, no-show rate), facility type breakdown, time-to-follow-up distribution |
| **No-Show Predictor** | Model performance metrics, coefficient chart, individual risk calculator with gauge, population probability distribution |

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Technology Stack

- **Database:** SQLite (demo) / MySQL 8.0 (production schema)
- **ORM / query layer:** SQLAlchemy 2.0 + pandas
- **Data generation:** Faker, NumPy
- **Modeling:** scikit-learn (LogisticRegression, DecisionTreeClassifier)
- **Visualization:** Plotly Express + Plotly Graph Objects
- **Dashboard:** Streamlit
- **Containerization:** Docker + Docker Compose

---

## Limitations

See [docs/limitations.md](docs/limitations.md) for a full discussion,
including synthetic-data caveats, model evaluation limitations, and
missing data considerations.

---

## Academic Context

This project extends database design work originally completed for BMIN 5020
(Biomedical Databases) at the University of Pennsylvania, Perelman School of
Medicine / School of Engineering. The original project designed and populated
a MySQL schema for HPV screening workflows using synthetic data in MySQL
Workbench. This repository re-implements and extends that work into a
production-style analytics engineering portfolio.

---

*Johanna Momole · Master of Biomedical Informatics · University of Pennsylvania*
