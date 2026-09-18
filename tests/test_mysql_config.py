from lmts.core.settings import MySQLSettings
from lmts.tools.mysql_config import render_db_php

def test_mysql_php_config_uses_settings() -> None:
    text = render_db_php(MySQLSettings(host='localhost', port=3307, database='lmts', username='lmts', password='lmts', publish_key='lmts'))
    assert "mysql:host=localhost;port=3307;dbname=lmts;charset=utf8mb4" in text
    assert "'user' => 'lmts'" in text
    assert "'password' => 'lmts'" in text
    assert "'publish_key' => 'lmts'" in text
