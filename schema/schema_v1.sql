-- LMTS canonical database schema
-- SSOT location: /schema/schema_v1.sql
-- Schema version: 1
-- Target: MariaDB / MySQL
--
-- No legacy compatibility layer exists. This file is the database SSOT.
-- Immutable report_json remains benchmark evidence truth.
-- report_*_index tables are derived/rebuildable projections only.

CREATE TABLE IF NOT EXISTS lmts_schema_version (
    component       VARCHAR(64) NOT NULL,
    schema_version  INT UNSIGNED NOT NULL,
    applied_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (component)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- USER / RESPONSIBILITY
-- Tier-4 is anonymous Reader state and has no users row.
-- Registered tiers: 3, 2, 1, 1337.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id          VARCHAR(128) NOT NULL,
    username         VARCHAR(128) NOT NULL,
    display_name     VARCHAR(255) NULL,
    organization     VARCHAR(255) NULL,
    tier             SMALLINT UNSIGNED NOT NULL DEFAULT 3,
    status           VARCHAR(32) NOT NULL DEFAULT 'active',
    verified         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_username (username),
    CONSTRAINT chk_users_tier CHECK (tier IN (1,2,3,1337))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_accounts (
    user_id          VARCHAR(128) NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    email            VARCHAR(320) NULL,
    account_status   VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_user_accounts_email (email),
    CONSTRAINT fk_user_accounts_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS invites (
    invite_id            VARCHAR(128) NOT NULL,
    owner_user_id        VARCHAR(128) NOT NULL,
    token_hash           VARCHAR(255) NOT NULL,
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at           DATETIME(6) NULL,
    status               VARCHAR(32) NOT NULL DEFAULT 'active',
    claimed_by_user_id   VARCHAR(128) NULL,
    claimed_at           DATETIME(6) NULL,
    PRIMARY KEY (invite_id),
    UNIQUE KEY uq_invites_token_hash (token_hash),
    KEY idx_invites_owner (owner_user_id),
    KEY idx_invites_claimed_by (claimed_by_user_id),
    CONSTRAINT fk_invites_owner
        FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_invites_claimed_by
        FOREIGN KEY (claimed_by_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tier_progression_requests (
    progression_id                   VARCHAR(128) NOT NULL,
    user_id                          VARCHAR(128) NOT NULL,
    current_tier                     SMALLINT UNSIGNED NOT NULL,
    requested_tier                   SMALLINT UNSIGNED NOT NULL,
    eligibility_status               VARCHAR(32) NOT NULL DEFAULT 'pending',
    eligibility_evidence_json        LONGTEXT NULL,
    approval_required_from_user_id   VARCHAR(128) NULL,
    status                           VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_at                       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    resolved_at                      DATETIME(6) NULL,
    PRIMARY KEY (progression_id),
    KEY idx_tier_progression_user (user_id),
    KEY idx_tier_progression_approver (approval_required_from_user_id),
    CONSTRAINT fk_tier_progression_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_tier_progression_approver
        FOREIGN KEY (approval_required_from_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_tier_progression_current CHECK (current_tier IN (1,2,3,1337)),
    CONSTRAINT chk_tier_progression_requested CHECK (requested_tier IN (1,2,3,1337)),
    CONSTRAINT chk_tier_progression_evidence CHECK (
        eligibility_evidence_json IS NULL OR JSON_VALID(eligibility_evidence_json)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_tier_history (
    history_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id              VARCHAR(128) NOT NULL,
    from_tier            SMALLINT UNSIGNED NOT NULL,
    to_tier              SMALLINT UNSIGNED NOT NULL,
    eligible_at          DATETIME(6) NULL,
    approved_by_user_id  VARCHAR(128) NULL,
    approved_at          DATETIME(6) NULL,
    rule_version         VARCHAR(128) NULL,
    reason_json          LONGTEXT NULL,
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (history_id),
    KEY idx_user_tier_history_user (user_id, created_at),
    CONSTRAINT fk_user_tier_history_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_user_tier_history_approver
        FOREIGN KEY (approved_by_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_user_tier_history_from CHECK (from_tier IN (1,2,3,1337)),
    CONSTRAINT chk_user_tier_history_to CHECK (to_tier IN (1,2,3,1337)),
    CONSTRAINT chk_user_tier_history_reason CHECK (
        reason_json IS NULL OR JSON_VALID(reason_json)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- CANONICAL HARDWARE
-- model -> component -> variant
-- resolution_type may be exact, partial or unknown.
-- Manual annotations never change canonical identity.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS hardware_nodes (
    hardware_id        VARCHAR(128) NOT NULL,
    category           VARCHAR(64) NOT NULL,
    level              VARCHAR(32) NOT NULL,
    parent_id          VARCHAR(128) NULL,
    canonical_key      VARCHAR(255) NOT NULL,
    label              VARCHAR(255) NOT NULL,
    vendor             VARCHAR(255) NULL,
    resolution_type    VARCHAR(32) NOT NULL DEFAULT 'exact',
    identity_json      LONGTEXT NOT NULL,
    profile_json       LONGTEXT NOT NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deprecated_at      DATETIME(6) NULL,
    replacement_id     VARCHAR(128) NULL,
    PRIMARY KEY (hardware_id),
    UNIQUE KEY uq_hardware_nodes_key (canonical_key),
    KEY idx_hardware_nodes_parent (parent_id),
    KEY idx_hardware_nodes_category_level (category, level),
    KEY idx_hardware_nodes_replacement (replacement_id),
    CONSTRAINT fk_hardware_nodes_parent
        FOREIGN KEY (parent_id) REFERENCES hardware_nodes(hardware_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_hardware_nodes_replacement
        FOREIGN KEY (replacement_id) REFERENCES hardware_nodes(hardware_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_hardware_nodes_level CHECK (level IN ('model','component','variant')),
    CONSTRAINT chk_hardware_nodes_resolution CHECK (resolution_type IN ('exact','partial','unknown')),
    CONSTRAINT chk_hardware_nodes_identity CHECK (JSON_VALID(identity_json)),
    CONSTRAINT chk_hardware_nodes_profile CHECK (JSON_VALID(profile_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS hardware_aliases (
    alias_id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    hardware_id       VARCHAR(128) NOT NULL,
    alias_type        VARCHAR(64) NOT NULL,
    normalized_value  VARCHAR(512) NOT NULL,
    raw_value         VARCHAR(512) NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (alias_id),
    UNIQUE KEY uq_hardware_alias (alias_type, normalized_value),
    KEY idx_hardware_alias_hardware (hardware_id),
    CONSTRAINT fk_hardware_alias_hardware
        FOREIGN KEY (hardware_id) REFERENCES hardware_nodes(hardware_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- SYSTEMS
-- A System is probed hardware. The user may label it, but does not manually
-- declare canonical hardware identity.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS systems (
    system_id             VARCHAR(128) NOT NULL,
    user_id               VARCHAR(128) NOT NULL,
    label                 VARCHAR(255) NOT NULL,
    system_class          VARCHAR(64) NULL,
    canonical_device_ref  VARCHAR(128) NULL,
    probe_version         VARCHAR(128) NULL,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_probed_at        DATETIME(6) NULL,
    updated_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (system_id),
    KEY idx_systems_user (user_id),
    KEY idx_systems_device (canonical_device_ref),
    CONSTRAINT fk_systems_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_systems_device
        FOREIGN KEY (canonical_device_ref) REFERENCES hardware_nodes(hardware_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS system_resources (
    system_resource_id  VARCHAR(128) NOT NULL,
    system_id           VARCHAR(128) NOT NULL,
    local_key           VARCHAR(128) NOT NULL,
    resource_kind       VARCHAR(64) NOT NULL,
    hardware_id         VARCHAR(128) NOT NULL,
    resolution_status   VARCHAR(32) NOT NULL,
    probe_data_json     LONGTEXT NOT NULL,
    user_annotation     VARCHAR(1024) NULL,
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (system_resource_id),
    UNIQUE KEY uq_system_resources_local (system_id, local_key),
    KEY idx_system_resources_hardware (hardware_id),
    CONSTRAINT fk_system_resources_system
        FOREIGN KEY (system_id) REFERENCES systems(system_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_system_resources_hardware
        FOREIGN KEY (hardware_id) REFERENCES hardware_nodes(hardware_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_system_resources_resolution CHECK (resolution_status IN ('exact','partial','unknown')),
    CONSTRAINT chk_system_resources_probe CHECK (JSON_VALID(probe_data_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS system_memory_pools (
    memory_pool_id     VARCHAR(128) NOT NULL,
    system_id          VARCHAR(128) NOT NULL,
    pool_kind          VARCHAR(32) NOT NULL,
    capacity_bytes     BIGINT UNSIGNED NOT NULL,
    properties_json    LONGTEXT NOT NULL,
    PRIMARY KEY (memory_pool_id),
    KEY idx_system_memory_pools_system (system_id),
    CONSTRAINT fk_system_memory_pools_system
        FOREIGN KEY (system_id) REFERENCES systems(system_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_system_memory_pools_kind CHECK (pool_kind IN ('system','dedicated','unified','other')),
    CONSTRAINT chk_system_memory_pools_properties CHECK (JSON_VALID(properties_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS system_memory_pool_access (
    memory_pool_id      VARCHAR(128) NOT NULL,
    system_resource_id  VARCHAR(128) NOT NULL,
    PRIMARY KEY (memory_pool_id, system_resource_id),
    CONSTRAINT fk_memory_pool_access_pool
        FOREIGN KEY (memory_pool_id) REFERENCES system_memory_pools(memory_pool_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_memory_pool_access_resource
        FOREIGN KEY (system_resource_id) REFERENCES system_resources(system_resource_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- COMPUTE PROFILES
-- Convenience presets selecting which System resources participate in tests.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS compute_profiles (
    compute_profile_id  VARCHAR(128) NOT NULL,
    user_id             VARCHAR(128) NOT NULL,
    system_id           VARCHAR(128) NOT NULL,
    name                VARCHAR(255) NOT NULL,
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (compute_profile_id),
    UNIQUE KEY uq_compute_profiles_name (user_id, system_id, name),
    KEY idx_compute_profiles_system (system_id),
    CONSTRAINT fk_compute_profiles_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_compute_profiles_system
        FOREIGN KEY (system_id) REFERENCES systems(system_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS compute_profile_resources (
    compute_profile_id  VARCHAR(128) NOT NULL,
    system_resource_id  VARCHAR(128) NOT NULL,
    configuration_json  LONGTEXT NULL,
    PRIMARY KEY (compute_profile_id, system_resource_id),
    CONSTRAINT fk_compute_profile_resources_profile
        FOREIGN KEY (compute_profile_id) REFERENCES compute_profiles(compute_profile_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_compute_profile_resources_resource
        FOREIGN KEY (system_resource_id) REFERENCES system_resources(system_resource_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_compute_profile_resources_config CHECK (
        configuration_json IS NULL OR JSON_VALID(configuration_json)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- CANONICAL MODEL CATALOG
-- family -> base -> branch -> provider_model -> variant -> artifact
-- Provider is part of canonical identity.
-- Quantization belongs to variant identity.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS model_providers (
    provider_id       VARCHAR(128) NOT NULL,
    canonical_key     VARCHAR(255) NOT NULL,
    name              VARCHAR(255) NOT NULL,
    properties_json   LONGTEXT NOT NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (provider_id),
    UNIQUE KEY uq_model_providers_key (canonical_key),
    CONSTRAINT chk_model_providers_properties CHECK (JSON_VALID(properties_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS model_nodes (
    model_node_id        VARCHAR(128) NOT NULL,
    level                VARCHAR(32) NOT NULL,
    parent_id            VARCHAR(128) NULL,
    provider_id          VARCHAR(128) NULL,
    canonical_key        VARCHAR(255) NOT NULL,
    label                VARCHAR(255) NOT NULL,
    resolution_type      VARCHAR(32) NOT NULL DEFAULT 'exact',
    identity_json        LONGTEXT NOT NULL,
    profile_json         LONGTEXT NOT NULL,
    created_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deprecated_at        DATETIME(6) NULL,
    replacement_id       VARCHAR(128) NULL,
    PRIMARY KEY (model_node_id),
    UNIQUE KEY uq_model_nodes_key (canonical_key),
    KEY idx_model_nodes_parent (parent_id),
    KEY idx_model_nodes_provider (provider_id),
    KEY idx_model_nodes_level (level),
    KEY idx_model_nodes_replacement (replacement_id),
    CONSTRAINT fk_model_nodes_parent
        FOREIGN KEY (parent_id) REFERENCES model_nodes(model_node_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_model_nodes_provider
        FOREIGN KEY (provider_id) REFERENCES model_providers(provider_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_model_nodes_replacement
        FOREIGN KEY (replacement_id) REFERENCES model_nodes(model_node_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_model_nodes_level CHECK (
        level IN ('family','base','branch','provider_model','variant','artifact')
    ),
    CONSTRAINT chk_model_nodes_resolution CHECK (resolution_type IN ('exact','partial','unknown')),
    CONSTRAINT chk_model_nodes_identity CHECK (JSON_VALID(identity_json)),
    CONSTRAINT chk_model_nodes_profile CHECK (JSON_VALID(profile_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS model_aliases (
    alias_id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    model_node_id     VARCHAR(128) NOT NULL,
    alias_type        VARCHAR(64) NOT NULL,
    normalized_value  VARCHAR(512) NOT NULL,
    raw_value         VARCHAR(512) NULL,
    created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (alias_id),
    UNIQUE KEY uq_model_alias (alias_type, normalized_value),
    KEY idx_model_alias_node (model_node_id),
    CONSTRAINT fk_model_alias_node
        FOREIGN KEY (model_node_id) REFERENCES model_nodes(model_node_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- USER-OWNED COMPOSITIONS
-- ===========================================================================

CREATE TABLE IF NOT EXISTS compositions (
    composition_id   VARCHAR(128) NOT NULL,
    user_id          VARCHAR(128) NOT NULL,
    name             VARCHAR(255) NOT NULL,
    description      TEXT NULL,
    definition_json  LONGTEXT NOT NULL,
    fingerprint      VARCHAR(255) NOT NULL,
    created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (composition_id),
    KEY idx_compositions_user (user_id),
    KEY idx_compositions_fingerprint (fingerprint),
    CONSTRAINT fk_compositions_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_compositions_definition CHECK (JSON_VALID(definition_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- DVS PRESETS
-- Tier-2+ may create/use private presets.
-- Tier-1+ may approve/publish preset versions to the public catalog.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS dvs_presets (
    preset_id        VARCHAR(128) NOT NULL,
    owner_user_id    VARCHAR(128) NOT NULL,
    name             VARCHAR(255) NOT NULL,
    description      TEXT NULL,
    created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (preset_id),
    KEY idx_dvs_presets_owner (owner_user_id),
    CONSTRAINT fk_dvs_presets_owner
        FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dvs_preset_versions (
    preset_version_id     VARCHAR(128) NOT NULL,
    preset_id             VARCHAR(128) NOT NULL,
    version               VARCHAR(64) NOT NULL,
    definition_json       LONGTEXT NOT NULL,
    fingerprint           VARCHAR(255) NOT NULL,
    created_by_user_id    VARCHAR(128) NOT NULL,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (preset_version_id),
    UNIQUE KEY uq_dvs_preset_version (preset_id, version),
    KEY idx_dvs_preset_versions_fingerprint (fingerprint),
    CONSTRAINT fk_dvs_preset_versions_preset
        FOREIGN KEY (preset_id) REFERENCES dvs_presets(preset_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_dvs_preset_versions_creator
        FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_dvs_preset_versions_definition CHECK (JSON_VALID(definition_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS dvs_preset_publications (
    preset_version_id      VARCHAR(128) NOT NULL,
    published_by_user_id   VARCHAR(128) NOT NULL,
    status                 VARCHAR(32) NOT NULL DEFAULT 'published',
    published_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (preset_version_id),
    KEY idx_dvs_publications_publisher (published_by_user_id),
    CONSTRAINT fk_dvs_publications_version
        FOREIGN KEY (preset_version_id) REFERENCES dvs_preset_versions(preset_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_dvs_publications_publisher
        FOREIGN KEY (published_by_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- CANONICAL TEST DEFINITIONS
-- Tier-1337 governs test content and semantics.
-- Parameter Sweep is a test kind, not a separate storage model.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS test_definitions (
    test_definition_id  VARCHAR(128) NOT NULL,
    namespace           VARCHAR(255) NOT NULL,
    name                VARCHAR(255) NOT NULL,
    description         TEXT NULL,
    category            VARCHAR(128) NULL,
    created_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (test_definition_id),
    UNIQUE KEY uq_test_definitions_namespace (namespace)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS test_versions (
    test_version_id       VARCHAR(128) NOT NULL,
    test_definition_id    VARCHAR(128) NOT NULL,
    version               VARCHAR(64) NOT NULL,
    kind                  VARCHAR(64) NOT NULL DEFAULT 'standard',
    definition_json       LONGTEXT NOT NULL,
    fingerprint           VARCHAR(255) NOT NULL,
    status                VARCHAR(32) NOT NULL DEFAULT 'candidate',
    created_by_user_id    VARCHAR(128) NULL,
    published_by_user_id  VARCHAR(128) NULL,
    created_at            DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    published_at          DATETIME(6) NULL,
    PRIMARY KEY (test_version_id),
    UNIQUE KEY uq_test_versions_version (test_definition_id, version),
    KEY idx_test_versions_fingerprint (fingerprint),
    KEY idx_test_versions_kind_status (kind, status),
    CONSTRAINT fk_test_versions_definition
        FOREIGN KEY (test_definition_id) REFERENCES test_definitions(test_definition_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_test_versions_creator
        FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_test_versions_publisher
        FOREIGN KEY (published_by_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_test_versions_definition CHECK (JSON_VALID(definition_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- CANONICAL TELEMETRY
-- Telemetry vocabulary is data, not schema. New telemetry types are inserted
-- into telemetry_types without changing the database structure.
-- Test versions declare which telemetry types they expect.
-- Telemetry values duplicate critical evidence context intentionally so
-- result queries do not depend on reconstructing ownership/topology joins.
-- ===========================================================================

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

-- Canonical telemetry vocabulary. Extend by INSERT, not ALTER TABLE.
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

-- ===========================================================================
-- IMMUTABLE REPORT STORE
-- report_json is evidence truth.
-- ===========================================================================

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

CREATE TABLE IF NOT EXISTS report_submissions (
    submission_id        VARCHAR(128) NOT NULL,
    report_id            VARCHAR(128) NOT NULL,
    submitter_user_id    VARCHAR(128) NULL,
    source               VARCHAR(128) NULL,
    verification_status  VARCHAR(32) NOT NULL DEFAULT 'unverified',
    received_at          DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (submission_id),
    KEY idx_report_submissions_report (report_id),
    KEY idx_report_submissions_submitter (submitter_user_id),
    CONSTRAINT fk_report_submissions_report
        FOREIGN KEY (report_id) REFERENCES reports(report_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_report_submissions_submitter
        FOREIGN KEY (submitter_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===========================================================================
-- DERIVED / REBUILDABLE REPORT INDEXES
-- These tables are query accelerators only and may be rebuilt from report_json.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS report_record_index (
    report_id                   VARCHAR(128) NOT NULL,
    record_id                   VARCHAR(128) NOT NULL,
    tester_user_id              VARCHAR(128) NULL,
    target_kind                 VARCHAR(32) NOT NULL,
    model_node_id               VARCHAR(128) NULL,
    composition_id              VARCHAR(128) NULL,
    test_version_id             VARCHAR(128) NULL,
    system_id                   VARCHAR(128) NULL,
    compute_profile_id          VARCHAR(128) NULL,
    started_at                  DATETIME(6) NULL,
    completed_at                DATETIME(6) NULL,
    duration_ms                 DECIMAL(20,6) NULL,
    ttft_ms                     DECIMAL(20,6) NULL,
    outcome                     VARCHAR(32) NULL,
    passed                      BOOLEAN NULL,
    score_percent               DECIMAL(12,6) NULL,
    runtime_configuration_json  LONGTEXT NULL,
    PRIMARY KEY (report_id, record_id),
    KEY idx_report_record_tester (tester_user_id),
    KEY idx_report_record_target (target_kind, model_node_id, composition_id),
    KEY idx_report_record_test (test_version_id),
    KEY idx_report_record_system (system_id),
    KEY idx_report_record_compute_profile (compute_profile_id),
    KEY idx_report_record_duration (duration_ms),
    KEY idx_report_record_outcome (outcome),
    CONSTRAINT fk_report_record_report
        FOREIGN KEY (report_id) REFERENCES reports(report_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_report_record_tester
        FOREIGN KEY (tester_user_id) REFERENCES users(user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_report_record_model
        FOREIGN KEY (model_node_id) REFERENCES model_nodes(model_node_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_report_record_test
        FOREIGN KEY (test_version_id) REFERENCES test_versions(test_version_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_report_record_runtime_config CHECK (
        runtime_configuration_json IS NULL OR JSON_VALID(runtime_configuration_json)
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

-- report_id + record_id is the immutable result identity. user_id, system_id,
-- compute_profile_id, test_definition_id and test_version_id are duplicated
-- deliberately as query-ready evidence context and must agree with report_json
-- when the projection is written or rebuilt.

CREATE TABLE IF NOT EXISTS report_record_hardware_index (
    report_id          VARCHAR(128) NOT NULL,
    record_id          VARCHAR(128) NOT NULL,
    resource_role      VARCHAR(128) NOT NULL,
    hardware_id        VARCHAR(128) NOT NULL,
    system_local_key   VARCHAR(128) NULL,
    PRIMARY KEY (report_id, record_id, resource_role, hardware_id),
    KEY idx_report_hardware_hardware (hardware_id),
    CONSTRAINT fk_report_hardware_record
        FOREIGN KEY (report_id, record_id)
        REFERENCES report_record_index(report_id, record_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT fk_report_hardware_hardware
        FOREIGN KEY (hardware_id) REFERENCES hardware_nodes(hardware_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO lmts_schema_version (component, schema_version)
VALUES ('database_ssot', 1)
ON DUPLICATE KEY UPDATE
    schema_version = VALUES(schema_version),
    applied_at = CURRENT_TIMESTAMP(6);
