-- LMTS development database convergence: observed report target identity
-- Date: 2026-09-27
-- Target: MariaDB / MySQL
--
-- Apply before deploying report projection code that writes target_ref/target_label:
--   sudo mariadb lmts < schema/2026-09-27_visualizer_targets.sql
--
-- /schema/schema_v1.sql remains the database SSOT for fresh databases.
--
-- target_ref and target_label are derived observations copied from immutable
-- lmts.report/1.1 evidence. They are not canonical model-resolution fields.
-- model_node_id/composition_id remain separate resolved references.

ALTER TABLE LMTS_report_record_index
    ADD COLUMN IF NOT EXISTS target_ref VARCHAR(255) NULL AFTER target_kind,
    ADD COLUMN IF NOT EXISTS target_label VARCHAR(255) NULL AFTER target_ref;

ALTER TABLE LMTS_report_record_index
    ADD INDEX IF NOT EXISTS idx_report_record_target_ref (target_kind, target_ref);
