-- LMTS-only migration: per-user/per-machine publish credentials
-- Date: 2026-09-29
-- Safe to re-run. This migration intentionally does not create, alter, reset
-- or otherwise own IAM tables.

CREATE TABLE IF NOT EXISTS LMTS_publish_keys (
    key_id          VARCHAR(128) NOT NULL,
    user_id         VARCHAR(128) NOT NULL,
    system_id       VARCHAR(128) NOT NULL,
    key_hash        CHAR(64) NOT NULL,
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_used_at    DATETIME(6) NULL,
    revoked_at      DATETIME(6) NULL,
    PRIMARY KEY (key_id),
    UNIQUE KEY uq_publish_keys_hash (key_hash),
    KEY idx_publish_keys_user_system (user_id, system_id),
    KEY idx_publish_keys_revoked (revoked_at),
    CONSTRAINT fk_publish_keys_user
        FOREIGN KEY (user_id) REFERENCES IAM_users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_publish_keys_system
        FOREIGN KEY (system_id) REFERENCES LMTS_systems(system_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Columns.
SET @sql = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'LMTS_report_submissions'
          AND COLUMN_NAME = 'submitter_system_id'
    ),
    'SELECT 1',
    'ALTER TABLE LMTS_report_submissions ADD COLUMN submitter_system_id VARCHAR(128) NULL AFTER submitter_user_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'LMTS_report_submissions'
          AND COLUMN_NAME = 'publish_key_id'
    ),
    'SELECT 1',
    'ALTER TABLE LMTS_report_submissions ADD COLUMN publish_key_id VARCHAR(128) NULL AFTER submitter_system_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Indexes.
SET @sql = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'LMTS_report_submissions'
          AND INDEX_NAME = 'idx_report_submissions_system'
    ),
    'SELECT 1',
    'ALTER TABLE LMTS_report_submissions ADD KEY idx_report_submissions_system (submitter_system_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'LMTS_report_submissions'
          AND INDEX_NAME = 'idx_report_submissions_publish_key'
    ),
    'SELECT 1',
    'ALTER TABLE LMTS_report_submissions ADD KEY idx_report_submissions_publish_key (publish_key_id)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Foreign keys.
SET @sql = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'LMTS_report_submissions'
          AND CONSTRAINT_NAME = 'fk_report_submissions_system'
          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
    ),
    'SELECT 1',
    'ALTER TABLE LMTS_report_submissions ADD CONSTRAINT fk_report_submissions_system FOREIGN KEY (submitter_system_id) REFERENCES LMTS_systems(system_id) ON UPDATE RESTRICT ON DELETE RESTRICT'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'LMTS_report_submissions'
          AND CONSTRAINT_NAME = 'fk_report_submissions_publish_key'
          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
    ),
    'SELECT 1',
    'ALTER TABLE LMTS_report_submissions ADD CONSTRAINT fk_report_submissions_publish_key FOREIGN KEY (publish_key_id) REFERENCES LMTS_publish_keys(key_id) ON UPDATE RESTRICT ON DELETE RESTRICT'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

INSERT INTO LMTS_schema_version (component, schema_version)
VALUES ('database_ssot', 2)
ON DUPLICATE KEY UPDATE
    schema_version = GREATEST(schema_version, VALUES(schema_version)),
    applied_at = CURRENT_TIMESTAMP(6);
