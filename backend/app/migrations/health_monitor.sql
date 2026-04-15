-- =============================================================================
-- EHUkene — Health Monitor
-- Contrato interno de integración backend · 2026-04-15
--
-- Aplicar manualmente:
--   psql -U ehukene -d ehukene -f migrations/health_monitor.sql
-- =============================================================================

CREATE TABLE IF NOT EXISTS health_cpu_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    load_percentage     SMALLINT        NULL CHECK (load_percentage BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX IF NOT EXISTS idx_health_cpu_device_time
    ON health_cpu_metrics (device_id, recorded_at DESC);


CREATE TABLE IF NOT EXISTS health_memory_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    total_kb            BIGINT          NULL CHECK (total_kb > 0),
    free_kb             BIGINT          NULL CHECK (free_kb >= 0),
    usage_pct           NUMERIC(5, 2)   NULL CHECK (usage_pct BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX IF NOT EXISTS idx_health_memory_device_time
    ON health_memory_metrics (device_id, recorded_at DESC);


CREATE TABLE IF NOT EXISTS health_disk_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    drive               VARCHAR(10)     NULL,
    total_gb            NUMERIC(10, 2)  NULL CHECK (total_gb > 0),
    free_gb             NUMERIC(10, 2)  NULL CHECK (free_gb >= 0),
    free_pct            NUMERIC(5, 2)   NULL CHECK (free_pct BETWEEN 0 AND 100),
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX IF NOT EXISTS idx_health_disk_device_time
    ON health_disk_metrics (device_id, recorded_at DESC);


CREATE TABLE IF NOT EXISTS health_event_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    critical_count      INTEGER         NOT NULL DEFAULT 0 CHECK (critical_count >= 0),
    error_count         INTEGER         NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    filtered_count      INTEGER         NOT NULL DEFAULT 0 CHECK (filtered_count >= 0),
    top_sources         JSONB           NOT NULL DEFAULT '[]'::jsonb,
    sample_events       JSONB           NOT NULL DEFAULT '[]'::jsonb,
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX IF NOT EXISTS idx_health_event_device_time
    ON health_event_metrics (device_id, recorded_at DESC);


CREATE TABLE IF NOT EXISTS health_domain_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    secure_channel      BOOLEAN         NOT NULL DEFAULT FALSE,
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX IF NOT EXISTS idx_health_domain_device_time
    ON health_domain_metrics (device_id, recorded_at DESC);


CREATE TABLE IF NOT EXISTS health_uptime_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_boot           TIMESTAMP       NULL,
    days                NUMERIC(5, 1)   NULL CHECK (days >= 0),
    status              VARCHAR(20)     NOT NULL,
    error_msg           TEXT            NULL
);

CREATE INDEX IF NOT EXISTS idx_health_uptime_device_time
    ON health_uptime_metrics (device_id, recorded_at DESC);


CREATE TABLE IF NOT EXISTS health_boot_time_metrics (
    id                      BIGSERIAL       PRIMARY KEY,
    device_id               UUID            NOT NULL REFERENCES devices(id),
    recorded_at             TIMESTAMP       NOT NULL,
    received_at             TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_boot_time          TIMESTAMP       NULL,
    boot_duration_seconds   INTEGER         NULL CHECK (boot_duration_seconds > 0),
    source                  VARCHAR(20)     NULL,
    status                  VARCHAR(20)     NOT NULL,
    error_msg               TEXT            NULL
);

CREATE INDEX IF NOT EXISTS idx_health_boot_time_device_time
    ON health_boot_time_metrics (device_id, recorded_at DESC);


CREATE TABLE IF NOT EXISTS health_service_metrics (
    id                  BIGSERIAL       PRIMARY KEY,
    device_id           UUID            NOT NULL REFERENCES devices(id),
    recorded_at         TIMESTAMP       NOT NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    service_name        VARCHAR(100)    NOT NULL,
    display_name        VARCHAR(255)    NULL,
    state               VARCHAR(50)     NOT NULL,
    startup_type        VARCHAR(50)     NULL,
    tier                SMALLINT        NOT NULL CHECK (tier BETWEEN 0 AND 3),
    status              VARCHAR(20)     NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_health_service_device_time
    ON health_service_metrics (device_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_service_device_name
    ON health_service_metrics (device_id, service_name, recorded_at DESC);
