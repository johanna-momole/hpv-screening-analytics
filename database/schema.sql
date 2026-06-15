-- HPV Screening Analytics Platform
-- MySQL 8.0 schema (production deployment)
-- For local demo, SQLite is used via SQLAlchemy in src/generate_data.py

CREATE DATABASE IF NOT EXISTS hpv_screening DEFAULT CHARACTER SET utf8mb4;
USE hpv_screening;

-- ─────────────────────────────────────────
-- Reference / lookup tables
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS insurance_type (
    insurance_plan_id   INT           NOT NULL AUTO_INCREMENT,
    plan_name           VARCHAR(100)  NOT NULL,
    coverage_type       VARCHAR(50)   NOT NULL,  -- Private, Medicaid, Medicare, CHIP, Self-Pay, ACA
    description         VARCHAR(255),
    PRIMARY KEY (insurance_plan_id),
    UNIQUE INDEX uq_plan_name (plan_name ASC)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS hospital (
    hospital_id     INT          NOT NULL AUTO_INCREMENT,
    hospital_name   VARCHAR(150) NOT NULL,
    type            VARCHAR(50)  NOT NULL,  -- Academic, Community, FQHC, etc.
    phone_number    VARCHAR(20),
    email           VARCHAR(100),
    PRIMARY KEY (hospital_id)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS screening_type (
    screening_type_id   INT          NOT NULL AUTO_INCREMENT,
    screening_name      VARCHAR(100) NOT NULL,
    description         VARCHAR(255),
    recommended_age_min INT,
    recommended_age_max INT,
    frequency_guideline INT,          -- months between screenings
    screening_modality  VARCHAR(50),  -- DNA, Cytology, Co-test, Colposcopy, Biopsy
    PRIMARY KEY (screening_type_id)
) ENGINE = InnoDB;

-- ─────────────────────────────────────────
-- Core entity tables
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS patient (
    patient_id          INT          NOT NULL AUTO_INCREMENT,
    insurance_plan_id   INT          NOT NULL,
    first_name          VARCHAR(50),
    last_name           VARCHAR(50),
    date_of_birth       DATE,
    gender              CHAR(1),      -- F, M, O (Other/Non-binary)
    ethnicity           VARCHAR(50),
    address             VARCHAR(150),
    zip_code            VARCHAR(10),
    education_level     VARCHAR(50),
    PRIMARY KEY (patient_id),
    INDEX idx_patient_insurance (insurance_plan_id ASC),
    CONSTRAINT fk_patient_insurance
        FOREIGN KEY (insurance_plan_id)
        REFERENCES insurance_type (insurance_plan_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS location (
    location_id     INT          NOT NULL AUTO_INCREMENT,
    hospital_id     INT          NOT NULL,
    address         VARCHAR(150),
    city            VARCHAR(100),
    state           CHAR(2),
    zip_code        VARCHAR(10),
    facility_type   VARCHAR(80),  -- Hospital Outpatient, FQHC, Private Practice, etc.
    PRIMARY KEY (location_id),
    INDEX idx_location_hospital (hospital_id ASC),
    CONSTRAINT fk_location_hospital
        FOREIGN KEY (hospital_id)
        REFERENCES hospital (hospital_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS provider (
    provider_id     INT          NOT NULL AUTO_INCREMENT,
    hospital_id     INT          NOT NULL,
    provider_name   VARCHAR(100),
    specialty       VARCHAR(80),  -- OB/GYN, Internal Medicine, Family Medicine, etc.
    email           VARCHAR(100),
    phone_number    VARCHAR(20),
    PRIMARY KEY (provider_id),
    INDEX idx_provider_hospital (hospital_id ASC),
    CONSTRAINT fk_provider_hospital
        FOREIGN KEY (hospital_id)
        REFERENCES hospital (hospital_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE = InnoDB;

-- ─────────────────────────────────────────
-- Transactional tables
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS appointment (
    appointment_id      INT          NOT NULL AUTO_INCREMENT,
    patient_id          INT          NOT NULL,
    insurance_plan_id   INT          NOT NULL,
    location_id         INT          NOT NULL,
    provider_id         INT          NOT NULL,
    screening_type_id   INT          NOT NULL,
    scheduled_date      DATE,
    status              VARCHAR(20)  NOT NULL DEFAULT 'Scheduled',  -- Completed, No-Show, Cancelled, Scheduled
    lead_time_days      INT,          -- days between booking and appointment
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (appointment_id),
    INDEX idx_appt_patient (patient_id ASC),
    INDEX idx_appt_provider (provider_id ASC),
    INDEX idx_appt_location (location_id ASC),
    INDEX idx_appt_screening_type (screening_type_id ASC),
    INDEX idx_appt_status (status ASC),
    INDEX idx_appt_scheduled_date (scheduled_date ASC),
    CONSTRAINT fk_appt_patient
        FOREIGN KEY (patient_id, insurance_plan_id)
        REFERENCES patient (patient_id, insurance_plan_id)  -- composite FK not standard in MySQL this way; see note below
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_appt_location
        FOREIGN KEY (location_id) REFERENCES location (location_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_appt_provider
        FOREIGN KEY (provider_id) REFERENCES provider (provider_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_appt_screening_type
        FOREIGN KEY (screening_type_id) REFERENCES screening_type (screening_type_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE = InnoDB;

-- Note: composite FK on (patient_id, insurance_plan_id) requires a composite index on the parent.
-- In production, add: ALTER TABLE patient ADD INDEX idx_patient_composite (patient_id, insurance_plan_id);

CREATE TABLE IF NOT EXISTS screening (
    screening_id        INT          NOT NULL AUTO_INCREMENT,
    appointment_id      INT          NOT NULL,
    screening_date      DATE,
    result              VARCHAR(20),  -- Negative, Positive, Inconclusive, Abnormal
    notes               TEXT,
    created_at          DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (screening_id),
    UNIQUE INDEX uq_screening_appt (appointment_id ASC),
    CONSTRAINT fk_screening_appointment
        FOREIGN KEY (appointment_id)
        REFERENCES appointment (appointment_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS follow_up (
    follow_up_id    INT          NOT NULL AUTO_INCREMENT,
    screening_id    INT          NOT NULL,
    follow_up_date  DATE,
    action_taken    VARCHAR(100),  -- Repeat Pap, Colposcopy, Biopsy, Referred, Watchful Waiting
    outcome         VARCHAR(50),   -- Resolved, Ongoing, Referred to Specialist, Lost to Follow-Up
    notes           TEXT,
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (follow_up_id),
    UNIQUE INDEX uq_followup_screening (screening_id ASC),
    INDEX idx_followup_date (follow_up_date ASC),
    CONSTRAINT fk_followup_screening
        FOREIGN KEY (screening_id)
        REFERENCES screening (screening_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE = InnoDB;
