-- LMTS-only migration: per-user/per-machine publish credentials
-- Date: 2026-09-29
-- Run once against the LMTS database. This migration intentionally does not
-- create, alter, reset or otherwise own IAM tables.

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

ALTER TABLE LMTS_report_submissions
    ADD COLUMN submitter_system_id VARCHAR(128) NULL AFTER submitter_user_id,
    ADD COLUMN publish_key_id VARCHAR(128) NULL AFTER submitter_system_id,
    ADD KEY idx_report_submissions_system (submitter_system_id),
    ADD KEY idx_report_submissions_publish_key (publish_key_id),
    ADD CONSTRAINT fk_report_submissions_system
        FOREIGN KEY (submitter_system_id) REFERENCES LMTS_systems(system_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    ADD CONSTRAINT fk_report_submissions_publish_key
        FOREIGN KEY (publish_key_id) REFERENCES LMTS_publish_keys(key_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

INSERT INTO LMTS_schema_version (component, schema_version)
VALUES ('database_ssot', 2)
ON DUPLICATE KEY UPDATE
    schema_version = GREATEST(schema_version, VALUES(schema_version)),
    applied_at = CURRENT_TIMESTAMP(6);
