#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root: sudo $0"
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="${SCRIPT_DIR}/schema_v1.sql"

DB_NAME="lmts"
DB_USER="lmts"
DB_HOST="localhost"
MYSQL_DATADIR="/home/lmts/mysql"
WWW_ROOT="/home/www"
LMTS_WEB="${WWW_ROOT}/lmts"
LMTS_PUBLIC="${LMTS_WEB}/public"
LMTS_CONFIG="${LMTS_WEB}/config"
AIGM_ROOT="${WWW_ROOT}/aigm.fi"
AIGM_PUBLIC="${AIGM_ROOT}/public"
APACHE_SITE="/etc/apache2/sites-available/000-aigm.conf"
MYSQL_CONFIG="/etc/mysql/mariadb.conf.d/99-lmts-datadir.cnf"
SECRETS_DIR="/etc/lmts"
SECRETS_FILE="${SECRETS_DIR}/bootstrap.env"

CALLER_USER="${SUDO_USER:-}"
if [[ -z "${CALLER_USER}" || "${CALLER_USER}" == "root" ]]; then
    echo "ERROR: run through sudo from the LMTS user so generated settings can be written to that account."
    exit 1
fi
CALLER_HOME="$(getent passwd "${CALLER_USER}" | cut -d: -f6)"
if [[ -z "${CALLER_HOME}" || ! -d "${CALLER_HOME}" ]]; then
    echo "ERROR: cannot resolve home directory for ${CALLER_USER}"
    exit 1
fi
SETTINGS_DIR="${CALLER_HOME}/.lmts"
SETTINGS_FILE="${SETTINGS_DIR}/settings.json"

if [[ ! -f "${SCHEMA_FILE}" ]]; then
    echo "ERROR: canonical LMTS schema not found: ${SCHEMA_FILE}"
    exit 1
fi

echo "[1/9] Installing privileged server packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    apache2 \
    mariadb-server \
    mariadb-client \
    php \
    libapache2-mod-php \
    php-mysql \
    python3 \
    rsync \
    openssl \
    acl

echo "[2/9] Preparing server directories..."
mkdir -p "${MYSQL_DATADIR}" "${LMTS_PUBLIC}" "${LMTS_CONFIG}" "${AIGM_PUBLIC}" "${SECRETS_DIR}"
chmod a+x /home
chmod 755 "${WWW_ROOT}" "${LMTS_WEB}" "${LMTS_PUBLIC}" "${AIGM_ROOT}" "${AIGM_PUBLIC}"
chown root:root /home/lmts
chmod 755 /home/lmts

echo "[3/9] Configuring MariaDB data directory..."
systemctl stop mariadb || true
MIGRATED_MYSQL=0
if [[ ! -d "${MYSQL_DATADIR}/mysql" ]]; then
    if [[ ! -d /var/lib/mysql/mysql ]]; then
        echo "ERROR: /var/lib/mysql does not contain an initialized MariaDB database."
        exit 1
    fi
    rsync -aH --numeric-ids /var/lib/mysql/ "${MYSQL_DATADIR}/"
    MIGRATED_MYSQL=1
fi
chown -R mysql:mysql "${MYSQL_DATADIR}"
chmod 750 "${MYSQL_DATADIR}"
cat > "${MYSQL_CONFIG}" <<EOF
[mysqld]
datadir=${MYSQL_DATADIR}
bind-address=127.0.0.1
EOF

mkdir -p /etc/systemd/system/mariadb.service.d
cat > /etc/systemd/system/mariadb.service.d/lmts-home.conf <<EOF
[Service]
ProtectHome=false
ReadWritePaths=${MYSQL_DATADIR}
EOF
mkdir -p /etc/systemd/system/apache2.service.d
cat > /etc/systemd/system/apache2.service.d/lmts-home.conf <<'EOF'
[Service]
ProtectHome=false
EOF
systemctl daemon-reload

if [[ -f /etc/apparmor.d/mariadbd ]]; then
    mkdir -p /etc/apparmor.d/local
    touch /etc/apparmor.d/local/mariadbd
    if ! grep -Fq "${MYSQL_DATADIR}/" /etc/apparmor.d/local/mariadbd; then
        cat >> /etc/apparmor.d/local/mariadbd <<EOF

# LMTS MariaDB datadir
${MYSQL_DATADIR}/ r,
${MYSQL_DATADIR}/** rwk,
EOF
    fi
    if command -v apparmor_parser >/dev/null 2>&1; then
        apparmor_parser -r /etc/apparmor.d/mariadbd || true
    fi
fi

echo "[4/9] Starting MariaDB..."
systemctl enable mariadb
systemctl restart mariadb
for _attempt in {1..20}; do
    if mariadb-admin --protocol=socket ping >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ! mariadb-admin --protocol=socket ping >/dev/null 2>&1; then
    echo "ERROR: MariaDB failed to start."
    systemctl status mariadb --no-pager || true
    journalctl -u mariadb -n 100 --no-pager || true
    exit 1
fi
ACTIVE_DATADIR="$(mariadb --protocol=socket -Nse 'SELECT @@datadir;' | head -n1)"
if [[ "${ACTIVE_DATADIR%/}" != "${MYSQL_DATADIR%/}" ]]; then
    echo "ERROR: MariaDB is not using ${MYSQL_DATADIR}"
    exit 1
fi
if [[ "${MIGRATED_MYSQL}" -eq 1 ]]; then
    find /var/lib/mysql -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    chown mysql:mysql /var/lib/mysql
fi

echo "[5/9] Generating/reusing LMTS credentials..."
umask 077
if [[ -f "${SECRETS_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${SECRETS_FILE}"
else
    DB_PASSWORD="$(openssl rand -hex 24)"
    PUBLISH_KEY="$(openssl rand -hex 32)"
    cat > "${SECRETS_FILE}" <<EOF
DB_PASSWORD=${DB_PASSWORD}
PUBLISH_KEY=${PUBLISH_KEY}
EOF
    chmod 600 "${SECRETS_FILE}"
fi
: "${DB_PASSWORD:?missing DB_PASSWORD in ${SECRETS_FILE}}"
: "${PUBLISH_KEY:?missing PUBLISH_KEY in ${SECRETS_FILE}}"

echo "[6/9] Creating LMTS database, account and schema..."
mariadb --protocol=socket <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM '${DB_USER}'@'localhost';
GRANT SELECT, INSERT ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
mariadb --protocol=socket "${DB_NAME}" < "${SCHEMA_FILE}"

echo "[7/9] Writing runtime database configuration..."
cat > "${LMTS_CONFIG}/db.php" <<PHP
<?php

return [
    'dsn' => 'mysql:host=${DB_HOST};dbname=${DB_NAME};charset=utf8mb4',
    'user' => '${DB_USER}',
    'password' => '${DB_PASSWORD}',
    'publish_key' => '${PUBLISH_KEY}',
];
PHP
chown root:www-data "${LMTS_CONFIG}/db.php"
chmod 640 "${LMTS_CONFIG}/db.php"
chmod 750 "${LMTS_CONFIG}"

mkdir -p "${SETTINGS_DIR}"
DB_HOST="${DB_HOST}" DB_NAME="${DB_NAME}" DB_USER="${DB_USER}" DB_PASSWORD="${DB_PASSWORD}" PUBLISH_KEY="${PUBLISH_KEY}" SETTINGS_FILE="${SETTINGS_FILE}" python3 <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ['SETTINGS_FILE'])
try:
    payload = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
except (OSError, ValueError, TypeError):
    payload = {}
if not isinstance(payload, dict):
    payload = {}
payload['schema_version'] = 2
payload.setdefault('output_folder', 'exports')
payload['mysql'] = {
    'host': os.environ['DB_HOST'],
    'database': os.environ['DB_NAME'],
    'username': os.environ['DB_USER'],
    'password': os.environ['DB_PASSWORD'],
    'publish_key': os.environ['PUBLISH_KEY'],
}
path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
PY
chown -R "${CALLER_USER}:${CALLER_USER}" "${SETTINGS_DIR}"
chmod 700 "${SETTINGS_DIR}"
chmod 600 "${SETTINGS_FILE}"

echo "[8/9] Configuring Apache host..."
cat > "${APACHE_SITE}" <<EOF
<VirtualHost *:80>
    ServerName aigm.fi
    ServerAlias www.aigm.fi
    DocumentRoot ${AIGM_PUBLIC}

    <Directory ${AIGM_PUBLIC}>
        Options FollowSymLinks
        AllowOverride None
        Require all granted
        DirectoryIndex index.html index.php
    </Directory>

    RedirectMatch 301 ^/benchmark$ /benchmark/
    Alias /benchmark/ ${LMTS_PUBLIC}/
    <Directory ${LMTS_PUBLIC}>
        Options FollowSymLinks
        AllowOverride None
        Require all granted
        DirectoryIndex index.html index.php
    </Directory>

    ErrorLog \${APACHE_LOG_DIR}/aigm-error.log
    CustomLog \${APACHE_LOG_DIR}/aigm-access.log combined
</VirtualHost>
EOF
a2dissite 000-default.conf >/dev/null 2>&1 || true
a2ensite 000-aigm.conf >/dev/null
apache2ctl configtest
systemctl enable apache2
systemctl restart apache2

setfacl -R -m "u:${CALLER_USER}:rwX" "${LMTS_WEB}"
find "${LMTS_WEB}" -type d -exec setfacl -m "d:u:${CALLER_USER}:rwx" {} \;

echo "[9/9] Verifying bootstrap..."
mariadb --protocol=socket "${DB_NAME}" -Nse "SELECT schema_version FROM lmts_schema_version WHERE component='result_server';"

cat <<EOF

LMTS privileged bootstrap complete.

Database : ${DB_NAME}
User     : ${DB_USER}
Host     : ${DB_HOST}
Schema   : v1
Settings : ${SETTINGS_FILE}
Web root : ${LMTS_PUBLIC}

The generated DB password and publish key were written to:
  ${SETTINGS_FILE}
  ${LMTS_CONFIG}/db.php

Secrets are not printed to stdout.
Deploy/update LMTS web application files from the TUI without sudo.
For an existing local or remote database, use TUI -> MySQL -> Install schema instead of this script.
EOF
