# LMTS PHP server package

Standalone PHP deployment surface for LMTS. The whole `php/` directory can be copied manually to a PHP server.

## Application directories

- `visualizer/` — read-only Results / Statistics UI and MariaDB-backed read API.
- `storage/` — authenticated report ingestion, immutable storage and relational projection.

Shared database configuration lives at `config.php` in the package root. Start from `config.example.php`.

## Requirements

- PHP 8.1+
- PDO
- PDO_MYSQL (`php-mysql` on Debian; PHP uses this driver with MariaDB)
- MariaDB with the canonical LMTS schema installed

No Composer dependencies are required.

The LMTS Python core remains zero-third-party-dependency Python. The PHP directory is a separate deployable artifact.
