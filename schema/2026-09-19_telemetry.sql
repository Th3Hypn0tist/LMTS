-- LMTS development database convergence: canonical telemetry
-- Date: 2026-09-19
-- Target: MariaDB / MySQL
--
-- Apply to an existing development database before continuing test data collection:
--   sudo mariadb lmts < schema/2026-09-19_telemetry.sql
--
-- This is a forward-only development convergence script. It does not drop data.
-- /schema/schema_v1.sql remains the database SSOT for fresh databases.

ALTER TABLE test_definitions
    ADD COLUMN IF NOT EXISTS description TEXT NULL AFTER name;

CREATE TABLE IF NOT EXISTS telemetry_types (
    telemetry_type_id  VARCHAR(128) NOT NULL,
    canonical_key      VARCHAR(255) NOT NULL,
    name               VARCHAR(255) NOT NULL,
    description        TEXT NULL,
    value_kind         VARCHAR(32) NOT NULL,
    unit               VARCHAR(64) NULL,
    definition_json    LONGTEXT NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deprecated_at      DATETIME(6) NULL,
    replacement_id     VARCHAR(128) NULL,
    PRIMARY KEY (telemetry_type_id),
    UNIQUE KEY uq_telemetry_types_key (canonical_key),
    KEY idx_telemetry_types_replacement (replacement_id),
    CONSTRAINT fk_telemetry_types_replacement
        FOREIGN KEY (replacement_id) REFERENCES telemetry_types(telemetry_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_telemetry_types_definition CHECK (
        definition_json IS NULL OR JSON_VALID(definition_json)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS test_version_telemetry_types (
    test_version_id     VARCHAR(128) NOT NULL,
    telemetry_type_id   VARCHAR(128) NOT NULL,
    required            BOOLEAN NOT NULL DEFAULT TRUE,
    ordinal             SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    configuration_json  LONGTEXT NULL,
    PRIMARY KEY (test_version_id, telemetry_type_id),
    KEY idx_test_version_telemetry_type (telemetry_type_id),
    CONSTRAINT fk_test_version_telemetry_test
        FOREIGN KEY (test_version_id) REFERENCES test_versions(test_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_test_version_telemetry_type
        FOREIGN KEY (telemetry_type_id) REFERENCES telemetry_types(telemetry_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_test_version_telemetry_config CHECK (
        configuration_json IS NULL OR JSON_VALID(configuration_json)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS telemetry_values (
    telemetry_value_id  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    report_id           VARCHAR(128) NOT NULL,
    record_id           VARCHAR(128) NOT NULL,
    user_id             VARCHAR(128) NOT NULL,
    system_id           VARCHAR(128) NOT NULL,
    compute_profile_id  VARCHAR(128) NULL,
    system_resource_id  VARCHAR(128) NULL,
    test_definition_id  VARCHAR(128) NOT NULL,
    test_version_id     VARCHAR(128) NOT NULL,
    telemetry_type_id   VARCHAR(128) NOT NULL,
    sample_ordinal      INT UNSIGNED NOT NULL DEFAULT 0,
    observed_at         DATETIME(6) NULL,
    value_number        DECIMAL(38,12) NULL,
    value_text          LONGTEXT NULL,
    value_boolean       BOOLEAN NULL,
    value_json          LONGTEXT NULL,
    unit_snapshot       VARCHAR(64) NULL,
    context_json        LONGTEXT NULL,
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (telemetry_value_id),
    KEY idx_telemetry_report_record (report_id, record_id),
    KEY idx_telemetry_user_test_type (user_id, test_definition_id, telemetry_type_id),
    KEY idx_telemetry_system_test_type (system_id, test_definition_id, telemetry_type_id),
    KEY idx_telemetry_compute_test_type (compute_profile_id, test_definition_id, telemetry_type_id),
    KEY idx_telemetry_test_version (test_version_id),
    KEY idx_telemetry_type (telemetry_type_id),
    KEY idx_telemetry_resource (system_resource_id),
    CONSTRAINT fk_telemetry_record
        FOREIGN KEY (report_id, record_id)
        REFERENCES report_record_index(report_id, record_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_system
        FOREIGN KEY (system_id) REFERENCES systems(system_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_compute_profile
        FOREIGN KEY (compute_profile_id) REFERENCES compute_profiles(compute_profile_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_system_resource
        FOREIGN KEY (system_resource_id) REFERENCES system_resources(system_resource_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_test_definition
        FOREIGN KEY (test_definition_id) REFERENCES test_definitions(test_definition_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_test_version
        FOREIGN KEY (test_version_id) REFERENCES test_versions(test_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_type
        FOREIGN KEY (telemetry_type_id) REFERENCES telemetry_types(telemetry_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_telemetry_value_json CHECK (
        value_json IS NULL OR JSON_VALID(value_json)
    ),
    CONSTRAINT chk_telemetry_context_json CHECK (
        context_json IS NULL OR JSON_VALID(context_json)
    ),
    CONSTRAINT chk_telemetry_value_present CHECK (
        value_number IS NOT NULL
        OR value_text IS NOT NULL
        OR value_boolean IS NOT NULL
        OR value_json IS NOT NULL
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Current canonical telemetry vocabulary. New telemetry is added by inserting
-- rows here; adding a telemetry type must not require a schema change.
INSERT INTO telemetry_types (
    telemetry_type_id, canonical_key, name, description, value_kind, unit
) VALUES
    ('input_tokens', 'input_tokens', 'Input tokens', 'Input token count for the executed record.', 'integer', 'tokens'),
    ('output_tokens', 'output_tokens', 'Output tokens', 'Output token count for the executed record.', 'integer', 'tokens'),
    ('ttft', 'ttft', 'Time to first token', 'Elapsed time to first generated token.', 'number', 'ms'),
    ('total_time', 'total_time', 'Total time', 'Total elapsed execution time.', 'number', 'ms'),
    ('score_percent', 'score_percent', 'Score percent', 'Normalized score when the test defines a percentage score.', 'number', 'percent'),
    ('workspace_protocol_steps', 'workspace_protocol_steps', 'Workspace protocol steps', 'Workspace protocol step count.', 'integer', 'steps'),
    ('output_file_count', 'output_file_count', 'Output file count', 'Number of output files produced by the record.', 'integer', 'files'),
    ('exact_output_match', 'exact_output_match', 'Exact output match', 'Whether output exactly matches the expected output.', 'boolean', NULL),
    ('cpu_util_percent', 'cpu_util_percent', 'CPU utilization', 'Observed CPU utilization.', 'number', 'percent'),
    ('memory_used_bytes', 'memory_used_bytes', 'Memory used', 'Observed system memory use.', 'integer', 'bytes'),
    ('gpu_util_percent', 'gpu_util_percent', 'GPU utilization', 'Observed GPU utilization for the referenced System resource.', 'number', 'percent'),
    ('gpu_memory_util_percent', 'gpu_memory_util_percent', 'GPU memory utilization', 'Observed GPU memory utilization for the referenced System resource.', 'number', 'percent'),
    ('gpu_memory_used_mib', 'gpu_memory_used_mib', 'GPU memory used', 'Observed GPU memory use for the referenced System resource.', 'number', 'MiB'),
    ('gpu_temperature_c', 'gpu_temperature_c', 'GPU temperature', 'Observed GPU temperature for the referenced System resource.', 'number', 'C'),
    ('gpu_power_w', 'gpu_power_w', 'GPU power', 'Observed GPU power draw for the referenced System resource.', 'number', 'W')
ON DUPLICATE KEY UPDATE
    canonical_key = VALUES(canonical_key),
    name = VALUES(name),
    description = VALUES(description),
    value_kind = VALUES(value_kind),
    unit = VALUES(unit);

-- record_id is the immutable report record/run identity. No separate run_id
-- or result_id is introduced: report_id + record_id identifies the result.
--
-- test_definition_id is duplicated beside test_version_id intentionally.
-- user_id, system_id and compute_profile_id are likewise stored directly on
-- the telemetry row. These are query-ready evidence context and must agree
-- with the report at write/import time.
