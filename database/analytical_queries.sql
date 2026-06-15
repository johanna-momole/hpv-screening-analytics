-- HPV Screening Analytics – Core Analytical Queries
-- Run against MySQL 8.0 using the views defined in views.sql

-- ─── 1. Patient census ───────────────────────────────────────────────────────
SELECT COUNT(DISTINCT patient_id) AS total_patients FROM patient;

-- ─── 2. Appointment volume by status ─────────────────────────────────────────
SELECT
    status,
    COUNT(*) AS total_appointments,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM appointment
GROUP BY status
ORDER BY total_appointments DESC;

-- ─── 3. Monthly appointment trend ────────────────────────────────────────────
SELECT
    DATE_FORMAT(scheduled_date, '%Y-%m') AS month,
    COUNT(*)                             AS appointments,
    SUM(CASE WHEN status = 'No-Show'    THEN 1 ELSE 0 END) AS no_shows,
    SUM(CASE WHEN status = 'Completed'  THEN 1 ELSE 0 END) AS completed
FROM appointment
WHERE scheduled_date IS NOT NULL
GROUP BY DATE_FORMAT(scheduled_date, '%Y-%m')
ORDER BY month;

-- ─── 4. Screening result distribution ────────────────────────────────────────
SELECT
    result,
    COUNT(*) AS n,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM screening
GROUP BY result
ORDER BY n DESC;

-- ─── 5. Follow-up completion rate after abnormal screening ───────────────────
SELECT
    COUNT(DISTINCT s.screening_id)  AS total_abnormal,
    COUNT(DISTINCT f.follow_up_id)  AS received_follow_up,
    ROUND(
        COUNT(DISTINCT f.follow_up_id)
        / NULLIF(COUNT(DISTINCT s.screening_id), 0) * 100, 1
    )                               AS follow_up_completion_pct
FROM screening s
LEFT JOIN follow_up f ON s.screening_id = f.screening_id
WHERE s.result IN ('Positive', 'Abnormal');

-- ─── 6. No-show rate by insurance coverage type ──────────────────────────────
SELECT
    i.coverage_type,
    COUNT(a.appointment_id)                                        AS total,
    SUM(CASE WHEN a.status = 'No-Show' THEN 1 ELSE 0 END)         AS no_shows,
    ROUND(
        SUM(CASE WHEN a.status = 'No-Show' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(a.appointment_id), 0) * 100, 1
    )                                                              AS no_show_rate_pct
FROM appointment a
JOIN insurance_type i ON a.insurance_plan_id = i.insurance_plan_id
GROUP BY i.coverage_type
ORDER BY no_show_rate_pct DESC;

-- ─── 7. Screening rate by education level ────────────────────────────────────
SELECT
    p.education_level,
    COUNT(DISTINCT p.patient_id)                        AS patients,
    COUNT(DISTINCT a.appointment_id)                    AS appointments,
    COUNT(DISTINCT s.screening_id)                      AS screenings_completed,
    ROUND(
        COUNT(DISTINCT s.screening_id)
        / NULLIF(COUNT(DISTINCT p.patient_id), 0), 2
    )                                                   AS screenings_per_patient
FROM patient p
LEFT JOIN appointment a ON p.patient_id = a.patient_id AND a.status = 'Completed'
LEFT JOIN screening   s ON a.appointment_id = s.appointment_id
GROUP BY p.education_level
ORDER BY screenings_per_patient DESC;

-- ─── 8. Provider workload and no-show burden ─────────────────────────────────
SELECT
    pr.provider_name,
    pr.specialty,
    COUNT(a.appointment_id)                                          AS total_appointments,
    SUM(CASE WHEN a.status = 'No-Show'   THEN 1 ELSE 0 END)         AS no_shows,
    SUM(CASE WHEN a.status = 'Completed' THEN 1 ELSE 0 END)         AS completed,
    ROUND(
        SUM(CASE WHEN a.status = 'No-Show' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(a.appointment_id), 0) * 100, 1
    )                                                                AS no_show_rate_pct
FROM provider pr
JOIN appointment a ON pr.provider_id = a.provider_id
GROUP BY pr.provider_id, pr.provider_name, pr.specialty
ORDER BY total_appointments DESC;

-- ─── 9. Abnormal screening rate by provider specialty ────────────────────────
SELECT
    pr.specialty,
    COUNT(s.screening_id)                                              AS total_screenings,
    SUM(CASE WHEN s.result IN ('Positive','Abnormal') THEN 1 ELSE 0 END) AS abnormal,
    ROUND(
        SUM(CASE WHEN s.result IN ('Positive','Abnormal') THEN 1 ELSE 0 END)
        / NULLIF(COUNT(s.screening_id), 0) * 100, 1
    )                                                                  AS abnormal_rate_pct
FROM provider pr
JOIN appointment a ON pr.provider_id   = a.provider_id
JOIN screening   s ON a.appointment_id = s.appointment_id
GROUP BY pr.specialty
ORDER BY abnormal_rate_pct DESC;

-- ─── 10. Geographic distribution by state and facility type ──────────────────
SELECT
    l.state,
    l.facility_type,
    COUNT(DISTINCT p.patient_id)     AS unique_patients,
    COUNT(a.appointment_id)          AS appointments
FROM location l
JOIN appointment a ON l.location_id  = a.location_id
JOIN patient    p ON a.patient_id    = p.patient_id
GROUP BY l.state, l.facility_type
ORDER BY l.state, appointments DESC;

-- ─── 11. Age-guideline compliance (screening at recommended age) ──────────────
SELECT
    st.screening_name,
    st.recommended_age_min,
    st.recommended_age_max,
    COUNT(s.screening_id)                               AS total_screenings,
    SUM(
        CASE WHEN
            TIMESTAMPDIFF(YEAR, p.date_of_birth, s.screening_date)
                BETWEEN st.recommended_age_min AND st.recommended_age_max
        THEN 1 ELSE 0 END
    )                                                   AS in_guideline_range,
    ROUND(
        SUM(
            CASE WHEN
                TIMESTAMPDIFF(YEAR, p.date_of_birth, s.screening_date)
                    BETWEEN st.recommended_age_min AND st.recommended_age_max
            THEN 1 ELSE 0 END
        ) / NULLIF(COUNT(s.screening_id), 0) * 100, 1
    )                                                   AS guideline_compliance_pct
FROM screening_type st
JOIN appointment    a  ON a.screening_type_id  = st.screening_type_id
JOIN screening      s  ON s.appointment_id     = a.appointment_id
JOIN patient        p  ON a.patient_id         = p.patient_id
GROUP BY st.screening_type_id, st.screening_name, st.recommended_age_min, st.recommended_age_max;

-- ─── 12. Time-to-follow-up after abnormal result ─────────────────────────────
SELECT
    ROUND(AVG(DATEDIFF(f.follow_up_date, s.screening_date)), 0) AS avg_days_to_followup,
    MIN(DATEDIFF(f.follow_up_date, s.screening_date))           AS min_days,
    MAX(DATEDIFF(f.follow_up_date, s.screening_date))           AS max_days,
    COUNT(f.follow_up_id)                                       AS follow_ups_with_date
FROM screening s
JOIN follow_up f ON s.screening_id = f.screening_id
WHERE s.result IN ('Positive', 'Abnormal')
  AND f.follow_up_date IS NOT NULL
  AND s.screening_date IS NOT NULL;
