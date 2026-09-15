-- LMTS result server schema
-- Schema version: 1

CREATE TABLE IF NOT EXISTS lmts_schema_version (
    component       VARCHAR(64) NOT NULL,
    schema_version  INT UNSIGNED NOT NULL,
    applied_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (component)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reports (
    report_id       VARCHAR(128) NOT NULL,
    report_type     VARCHAR(64) NOT NULL,
    created_at      DATETIME(6) NOT NULL,
    source_type     VARCHAR(128) NOT NULL,
    source_id       VARCHAR(255) NOT NULL,
    report_json     LONGTEXT NOT NULL,
    imported_at     DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (report_id),
    INDEX idx_reports_created (created_at),
    INDEX idx_reports_source (source_type, source_id),
    CONSTRAINT chk_report_json CHECK (JSON_VALID(report_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO lmts_schema_version (component, schema_version)
VALUES ('result_server', 1)
ON DUPLICATE KEY UPDATE
    schema_version = VALUES(schema_version),
    applied_at = CURRENT_TIMESTAMP(6);
