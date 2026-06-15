-- Analytical views for HPV Screening Analytics Platform
-- Compatible with MySQL 8.0 and SQLite (with minor dialect adjustments)

-- ─────────────────────────────────────────
-- View 1: Patient demographics + insurance
-- ─────────────────────────────────────────
CREATE OR REPLACE VIEW v_patient_insurance AS
SELECT
    p.patient_id,
    CONCAT(p.first_name, ' ', p.last_name)  AS patient_name,
    p.date_of_birth,
    TIMESTAMPDIFF(YEAR, p.date_of_birth, CURDATE()) AS age_years,
    p.gender,
    p.ethnicity,
    p.zip_code,
    p.education_level,
    i.plan_name          AS insurance_name,
    i.coverage_type
FROM patient p
LEFT JOIN insurance_type i ON p.insurance_plan_id = i.insurance_plan_id;

-- ─────────────────────────────────────────
-- View 2: Appointment + location + facility
-- ─────────────────────────────────────────
CREATE OR REPLACE VIEW v_appointment_location AS
SELECT
    a.appointment_id,
    a.scheduled_date,
    a.status,
    a.lead_time_days,
    l.address           AS location_address,
    l.city,
    l.state,
    l.zip_code          AS facility_zip,
    l.facility_type,
    h.hospital_name
FROM appointment a
JOIN location l  ON a.location_id  = l.location_id
JOIN hospital h  ON l.hospital_id  = h.hospital_id;

-- ─────────────────────────────────────────
-- View 3: Screening detail with type + patient
-- ─────────────────────────────────────────
CREATE OR REPLACE VIEW v_screening_detail AS
SELECT
    s.screening_id,
    s.appointment_id,
    s.screening_date,
    s.result,
    st.screening_name,
    st.screening_modality,
    st.recommended_age_min,
    st.recommended_age_max,
    p.patient_id,
    p.gender,
    TIMESTAMPDIFF(YEAR, p.date_of_birth, s.screening_date) AS age_at_screening
FROM screening s
JOIN appointment  a  ON s.appointment_id  = a.appointment_id
JOIN screening_type st ON a.screening_type_id = st.screening_type_id
JOIN patient      p  ON a.patient_id      = p.patient_id;

-- ─────────────────────────────────────────
-- View 4: Provider screening activity
-- ─────────────────────────────────────────
CREATE OR REPLACE VIEW v_provider_activity AS
SELECT
    pr.provider_id,
    pr.provider_name,
    pr.specialty,
    COUNT(s.screening_id)                                             AS total_screenings,
    SUM(CASE WHEN s.result IN ('Positive','Abnormal') THEN 1 ELSE 0 END) AS abnormal_screenings,
    ROUND(
        SUM(CASE WHEN s.result IN ('Positive','Abnormal') THEN 1 ELSE 0 END)
        / NULLIF(COUNT(s.screening_id), 0) * 100, 2
    )                                                                 AS abnormal_rate_pct,
    COUNT(a.appointment_id)                                           AS total_appointments,
    SUM(CASE WHEN a.status = 'No-Show' THEN 1 ELSE 0 END)            AS no_shows,
    ROUND(
        SUM(CASE WHEN a.status = 'No-Show' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(a.appointment_id), 0) * 100, 2
    )                                                                 AS no_show_rate_pct
FROM provider pr
JOIN appointment a ON pr.provider_id = a.provider_id
LEFT JOIN screening s ON a.appointment_id = s.appointment_id
GROUP BY pr.provider_id, pr.provider_name, pr.specialty;

-- ─────────────────────────────────────────
-- View 5: Appointment overview (timeliness)
-- ─────────────────────────────────────────
CREATE OR REPLACE VIEW v_appointment_overview AS
SELECT
    a.appointment_id,
    a.scheduled_date,
    a.status,
    a.lead_time_days,
    CONCAT(p.first_name, ' ', p.last_name) AS patient_name,
    p.gender,
    p.ethnicity,
    p.education_level,
    i.coverage_type                        AS insurance_type,
    pr.provider_name,
    pr.specialty,
    l.facility_type,
    l.state
FROM appointment a
JOIN patient       p  ON a.patient_id        = p.patient_id
JOIN insurance_type i  ON a.insurance_plan_id  = i.insurance_plan_id
JOIN provider      pr ON a.provider_id        = pr.provider_id
JOIN location      l  ON a.location_id        = l.location_id;
