# Storage

Authenticated LMTS result ingestion for the standalone PHP package.

- `report.php` accepts LMTS benchmark reports with `POST`.
- `X-LMTS-Key` must match `publish_key` in `../config.php`.
- Reports are stored immutably in MariaDB.
- `GET report.php?id=<report_id>` is available for publish verification.

This directory owns result storage only. Visualization lives in `../visualizer/`.
