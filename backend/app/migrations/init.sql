-- =============================================================================
-- EHUkene — Schema inicial (POC)
-- Contratos v1.3 · 2026-03-30
--
-- Aplicar manualmente:
--   psql -U ehukene -d ehukene -f migrations/init.sql
-- =============================================================================

-- Extensión para gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- devices
-- =============================================================================
CREATE TABLE IF NOT EXISTS devices (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    hostname        VARCHAR(255)    NOT NULL,
    api_key_hash    VARCHAR(64)     NOT NULL,       -- SHA-256 hex de la API Key
    first_seen      TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMP       NOT NULL DEFAULT NOW(),
    active          BOOLEAN         NOT NULL DEFAULT TRUE,
    agent_version   VARCHAR(20)     NULL            -- Última versión reportada
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_hostname ON devices (hostname);
CREATE INDEX        IF NOT EXISTS idx_devices_active   ON devices (active);

-- =============================================================================
-- telemetry_raw
-- =============================================================================
CREATE TABLE IF NOT EXISTS telemetry_raw (
    id          BIGSERIAL       PRIMARY KEY,
    device_id   UUID            NOT NULL REFERENCES devices(id),
    agent_timestamp TIMESTAMP   NOT NULL,
    received_at TIMESTAMP       NOT NULL DEFAULT NOW(),
    payload     JSONB           NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_raw_device_time
    ON telemetry_raw (device_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_raw_device_agent_time
    ON telemetry_raw (device_id, agent_timestamp DESC);

-- =============================================================================
-- battery_metrics
-- =============================================================================
CREATE TABLE IF NOT EXISTS battery_metrics (
    id                          BIGSERIAL       PRIMARY KEY,
    device_id                   UUID            NOT NULL REFERENCES devices(id),
    recorded_at                 TIMESTAMP       NOT NULL,
    received_at                 TIMESTAMP       NOT NULL DEFAULT NOW(),
    data_source                 VARCHAR(10)     NOT NULL,   -- 'powercfg' | 'wmi'
    battery_name                VARCHAR(100)    NULL,
    battery_manufacturer        VARCHAR(100)    NULL,
    battery_serial              VARCHAR(50)     NULL,
    battery_chemistry           VARCHAR(10)     NULL,
    design_capacity_wh          NUMERIC(10, 3)  NOT NULL CHECK (design_capacity_wh > 0),
    full_charge_capacity_wh     NUMERIC(10, 3)  NOT NULL CHECK (full_charge_capacity_wh >= 0),
    health_percent              NUMERIC(5, 2)   NOT NULL CHECK (health_percent BETWEEN 0 AND 150),
    battery_status              SMALLINT        NULL
);

CREATE INDEX IF NOT EXISTS idx_battery_device_time
    ON battery_metrics (device_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_battery_health
    ON battery_metrics (device_id, health_percent);

-- =============================================================================
-- software_usage
-- =============================================================================
CREATE TABLE IF NOT EXISTS software_usage (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    software_name       VARCHAR(100)    NOT NULL,
    installed           BOOLEAN         NOT NULL,
    version             VARCHAR(50)     NULL,
    last_execution      TIMESTAMP       NULL,
    executions_30d      INTEGER         NOT NULL DEFAULT 0 CHECK (executions_30d >= 0),
    executions_60d      INTEGER         NOT NULL DEFAULT 0 CHECK (executions_60d >= 0),
    executions_90d      INTEGER         NOT NULL DEFAULT 0 CHECK (executions_90d >= 0)
);

CREATE INDEX IF NOT EXISTS idx_software_device_name_time
    ON software_usage (device_id, software_name, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_software_name_installed
    ON software_usage (software_name, installed);

-- =============================================================================
-- boot_metrics
-- =============================================================================
CREATE TABLE IF NOT EXISTS boot_metrics (
    id                      BIGSERIAL       PRIMARY KEY,
    device_id               UUID            NOT NULL REFERENCES devices(id),
    recorded_at             TIMESTAMP       NOT NULL,
    received_at             TIMESTAMP       NOT NULL DEFAULT NOW(),
    data_source             VARCHAR(15)     NOT NULL,   -- 'event_log' | 'wmi'
    last_boot_time          TIMESTAMP       NOT NULL,
    boot_duration_seconds   INTEGER         NULL CHECK (boot_duration_seconds > 0)
);

CREATE INDEX IF NOT EXISTS idx_boot_device_time
    ON boot_metrics (device_id, recorded_at DESC);

-- =============================================================================
-- disk_metrics
-- =============================================================================
CREATE TABLE IF NOT EXISTS disk_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    data_source         VARCHAR(10)     NOT NULL,   -- 'cim'
    drive_letter        VARCHAR(10)     NOT NULL,
    volume_name         VARCHAR(255)    NULL,
    filesystem          VARCHAR(20)     NULL,
    total_capacity_gb   NUMERIC(10, 3)  NOT NULL CHECK (total_capacity_gb > 0),
    free_capacity_gb    NUMERIC(10, 3)  NOT NULL CHECK (free_capacity_gb >= 0),
    used_capacity_gb    NUMERIC(10, 3)  NOT NULL CHECK (used_capacity_gb >= 0),
    used_percent        NUMERIC(5, 2)   NOT NULL CHECK (used_percent BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_disk_device_time
    ON disk_metrics (device_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_disk_device_drive
    ON disk_metrics (device_id, drive_letter, recorded_at DESC);

-- =============================================================================
-- agent_versions  (Fase 2 — auto-update; tabla creada en POC, sin datos)
-- =============================================================================
CREATE TABLE IF NOT EXISTS agent_versions (
    id              SERIAL          PRIMARY KEY,
    version         VARCHAR(20)     NOT NULL,
    artifact_type   VARCHAR(20)     NOT NULL,   -- 'core' | 'plugin'
    artifact_name   VARCHAR(100)    NOT NULL,
    download_url    VARCHAR(500)    NOT NULL,
    checksum_sha256 VARCHAR(64)     NOT NULL,
    published_at    TIMESTAMP       NOT NULL DEFAULT NOW(),
    active          BOOLEAN         NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_versions_active
    ON agent_versions (artifact_type, artifact_name, active)
    WHERE active = TRUE;
