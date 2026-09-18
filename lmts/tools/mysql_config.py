from __future__ import annotations

from lmts.core.settings import MySQLSettings

from .output import OutputTarget, write_files


def _php_single_quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def render_db_php(mysql: MySQLSettings) -> str:
    host = _php_single_quoted(mysql.host)
    database = _php_single_quoted(mysql.database)
    username = _php_single_quoted(mysql.username)
    password = _php_single_quoted(mysql.password)
    publish_key = _php_single_quoted(mysql.publish_key)
    return (
        "<?php\n\n"
        "return [\n"
        f"    'dsn' => 'mysql:host={host};port={mysql.port};dbname={database};charset=utf8mb4',\n"
        f"    'user' => '{username}',\n"
        f"    'password' => '{password}',\n"
        f"    'publish_key' => '{publish_key}',\n"
        "];\n"
    )


def deploy_mysql_config(target: OutputTarget, mysql: MySQLSettings) -> list[str]:
    return write_files(target, {'config/db.php': render_db_php(mysql)})
