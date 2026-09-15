#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root: sudo $0"
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="${SCRIPT_DIR}/schema_v1.sql"
SCHEMA_VERSION=1

DB_NAME="lmts"
DB_USER="lmts"
DB_HOST="localhost"
MYSQL_DATADIR="/home/lmts/mysql"
WWW_ROOT="/home/www"
LMTS_WEB="${WWW_ROOT}/lmts"
LMTS_CONFIG="${LMTS_WEB}/config"
AIGM_ROOT="${WWW_ROOT}/aigm.fi"
AIGM_PUBLIC="${AIGM_ROOT}/public"
APACHE_SITE="/etc/apache2/sites-available/000-aigm.conf"
MYSQL_CONFIG="/etc/mysql/mariadb.conf.d/99-lmts-datadir.cnf"
MARIADB_OVERRIDE="/etc/systemd/system/mariadb.service.d/lmts-home.conf"
APACHE_OVERRIDE="/etc/systemd/system/apache2.service.d/lmts-home.conf"
APPARMOR_LOCAL="/etc/apparmor.d/local/mariadbd"
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

CHANGED=0
INSTALLED=0
RESTARTED=0
UNCHANGED=0

changed() {
    CHANGED=$((CHANGED + 1))
    echo "  changed: $*"
}

installed() {
    INSTALLED=$((INSTALLED + 1))
    echo "  installed: $*"
}

restarted() {
    RESTARTED=$((RESTARTED + 1))
    echo "  restarted: $*"
}

unchanged() {
    UNCHANGED=$((UNCHANGED + 1))
    echo "  unchanged: $*"
}

write_if_changed() {
    local path="$1"
    local mode="$2"
    local owner="$3"
    local group="$4"
    local temp
    temp="$(mktemp)"
    cat > "${temp}"
    if [[ -f "${path}" ]] && cmp -s "${temp}" "${path}"; then
        rm -f "${temp}"
        chmod "${mode}" "${path}"
        chown "${owner}:${group}" "${path}"
        return 1
    fi
    install -D -m "${mode}" -o "${owner}" -g "${group}" "${temp}" "${path}"
    rm -f "${temp}"
    return 0
}

service_active() {
    systemctl is-active --quiet "$1"
}

service_enabled() {
    systemctl is-enabled --quiet "$1" 2>/dev/null
}

echo "============================================================"
echo " LMTS privileged server bootstrap"
echo " converge-to-state mode"
echo "============================================================"

# ------------------------------------------------------------
# 1. Packages: install only what is missing.
# ------------------------------------------------------------
echo "[1/9] Checking privileged server packages..."
PACKAGES=(
    apache2
    mariadb-server
    mariadb-client
    php
    libapache2-mod-php
    php-mysql
    python3
    rsync
    openssl
    acl
)
MISSING_PACKAGES=()
for package in "${PACKAGES[@]}"; do
    if ! dpkg-query -W -f='${Status}' "${package}" 2>/dev/null | grep -q '^install ok installed$'; then
        MISSING_PACKAGES+=("${package}")
    fi
done
if (( ${#MISSING_PACKAGES[@]} > 0 )); then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y "${MISSING_PACKAGES[@]}"
    installed "packages: ${MISSING_PACKAGES[*]}"
else
    unchanged "server packages"
fi

# ------------------------------------------------------------
# 2. Directories and credentials.
# ------------------------------------------------------------
echo "[2/9] Checking directories and bootstrap credentials..."
for directory in "${MYSQL_DATADIR}" "${LMTS_WEB}" "${LMTS_CONFIG}" "${AIGM_PUBLIC}" "${SECRETS_DIR}"; do
    if [[ ! -d "${directory}" ]]; then
        mkdir -p "${directory}"
        changed "created ${directory}"
    fi
done
chmod a+x /home
chmod 755 "${WWW_ROOT}" "${LMTS_WEB}" "${AIGM_ROOT}" "${AIGM_PUBLIC}"
chown root:root /home/lmts
chmod 755 /home/lmts

umask 077
if [[ -f "${SECRETS_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${SECRETS_FILE}"
    unchanged "bootstrap credentials"
else
    DB_PASSWORD="$(openssl rand -hex 24)"
    PUBLISH_KEY="$(openssl rand -hex 32)"
    cat > "${SECRETS_FILE}" <<EOF
DB_PASSWORD=${DB_PASSWORD}
PUBLISH_KEY=${PUBLISH_KEY}
EOF
    chmod 600 "${SECRETS_FILE}"
    chown root:root "${SECRETS_FILE}"
    changed "generated bootstrap credentials"
fi
: "${DB_PASSWORD:?missing DB_PASSWORD in ${SECRETS_FILE}}"
: "${PUBLISH_KEY:?missing PUBLISH_KEY in ${SECRETS_FILE}}"

# ------------------------------------------------------------
# 3. MariaDB datadir and service policy.
# ------------------------------------------------------------
echo "[3/9] Checking MariaDB data directory and service policy..."
MARIADB_RESTART_REQUIRED=0
SYSTEMD_RELOAD_REQUIRED=0
APPARMOR_RELOAD_REQUIRED=0
MIGRATED_MYSQL=0

if [[ ! -d "${MYSQL_DATADIR}/mysql" ]]; then
    if [[ ! -d /var/lib/mysql/mysql ]]; then
        echo "ERROR: neither ${MYSQL_DATADIR} nor /var/lib/mysql contains an initialized MariaDB database."
        exit 1
    fi
    if service_active mariadb; then
        systemctl stop mariadb
    fi
    rsync -aH --numeric-ids /var/lib/mysql/ "${MYSQL_DATADIR}/"
    MIGRATED_MYSQL=1
    MARIADB_RESTART_REQUIRED=1
    changed "migrated MariaDB data to ${MYSQL_DATADIR}"
else
    unchanged "MariaDB data already in ${MYSQL_DATADIR}"
fi
chown -R mysql:mysql "${MYSQL_DATADIR}"
chmod 750 "${MYSQL_DATADIR}"

if write_if_changed "${MYSQL_CONFIG}" 644 root root <<EOF
[mysqld]
datadir=${MYSQL_DATADIR}
bind-address=127.0.0.1
EOF
then
    MARIADB_RESTART_REQUIRED=1
    changed "MariaDB datadir configuration"
else
    unchanged "MariaDB datadir configuration"
fi

if write_if_changed "${MARIADB_OVERRIDE}" 644 root root <<EOF
[Service]
ProtectHome=false
ReadWritePaths=${MYSQL_DATADIR}
EOF
then
    SYSTEMD_RELOAD_REQUIRED=1
    MARIADB_RESTART_REQUIRED=1
    changed "MariaDB systemd override"
else
    unchanged "MariaDB systemd override"
fi

if write_if_changed "${APACHE_OVERRIDE}" 644 root root <<'EOF'
[Service]
ProtectHome=false
EOF
then
    SYSTEMD_RELOAD_REQUIRED=1
    changed "Apache systemd override"
else
    unchanged "Apache systemd override"
fi

if [[ -f /etc/apparmor.d/mariadbd ]]; then
    mkdir -p /etc/apparmor.d/local
    touch "${APPARMOR_LOCAL}"
    if ! grep -Fq "${MYSQL_DATADIR}/" "${APPARMOR_LOCAL}"; then
        cat >> "${APPARMOR_LOCAL}" <<EOF

# LMTS MariaDB datadir
${MYSQL_DATADIR}/ r,
${MYSQL_DATADIR}/** rwk,
EOF
        APPARMOR_RELOAD_REQUIRED=1
        MARIADB_RESTART_REQUIRED=1
        changed "MariaDB AppArmor local policy"
    else
        unchanged "MariaDB AppArmor local policy"
    fi
fi

if (( SYSTEMD_RELOAD_REQUIRED )); then
    systemctl daemon-reload
fi
if (( APPARMOR_RELOAD_REQUIRED )) && command -v apparmor_parser >/dev/null 2>&1; then
    apparmor_parser -r /etc/apparmor.d/mariadbd
fi

# ------------------------------------------------------------
# 4. MariaDB lifecycle: restart only when policy changed.
# ------------------------------------------------------------
echo "[4/9] Converging MariaDB service..."
if ! service_enabled mariadb; then
    systemctl enable mariadb
    changed "enabled MariaDB service"
fi
if service_active mariadb; then
    if (( MARIADB_RESTART_REQUIRED )); then
        systemctl restart mariadb
        restarted "MariaDB"
    else
        unchanged "MariaDB service already active"
    fi
else
    systemctl start mariadb
    restarted "MariaDB started"
fi

for _attempt in {1..20}; do
    if mariadb-admin --protocol=socket ping >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
if ! mariadb-admin --protocol=socket ping >/dev/null 2>&1; then
    echo "ERROR: MariaDB failed to become ready."
    systemctl status mariadb --no-pager || true
    journalctl -u mariadb -n 100 --no-pager || true
    exit 1
fi
ACTIVE_DATADIR="$(mariadb --protocol=socket -Nse 'SELECT @@datadir;' | head -n1)"
if [[ "${ACTIVE_DATADIR%/}" != "${MYSQL_DATADIR%/}" ]]; then
    echo "ERROR: MariaDB is not using ${MYSQL_DATADIR}"
    exit 1
fi
if (( MIGRATED_MYSQL )); then
    find /var/lib/mysql -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    chown mysql:mysql /var/lib/mysql
    changed "removed migrated source data from /var/lib/mysql"
fi

# ------------------------------------------------------------
# 5. Database, runtime account and least-privilege grants.
# ------------------------------------------------------------
echo "[5/9] Converging LMTS database and runtime account..."
DB_EXISTS="$(mariadb --protocol=socket -Nse "SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='${DB_NAME}';")"
if [[ "${DB_EXISTS}" != "1" ]]; then
    mariadb --protocol=socket -e "CREATE DATABASE \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    changed "created database ${DB_NAME}"
else
    unchanged "database ${DB_NAME}"
fi

USER_EXISTS="$(mariadb --protocol=socket -Nse "SELECT COUNT(*) FROM mysql.user WHERE User='${DB_USER}' AND Host='localhost';")"
if [[ "${USER_EXISTS}" != "1" ]]; then
    mariadb --protocol=socket -e "CREATE USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
    changed "created database runtime account"
else
    if ! MYSQL_PWD="${DB_PASSWORD}" mariadb --protocol=tcp --host=127.0.0.1 --user="${DB_USER}" -Nse 'SELECT 1;' >/dev/null 2>&1; then
        mariadb --protocol=socket -e "ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
        changed "synchronized database runtime password"
    else
        unchanged "database runtime password"
    fi
fi

GRANTS="$(mariadb --protocol=socket -Nse "SHOW GRANTS FOR '${DB_USER}'@'localhost';")"
EXPECTED_GRANT="GRANT SELECT, INSERT ON \`${DB_NAME}\`.* TO \`${DB_USER}\`@\`localhost\`"
if [[ "${GRANTS}" != *"${EXPECTED_GRANT}"* ]] || echo "${GRANTS}" | grep -Eq "GRANT .* (UPDATE|DELETE|CREATE|DROP|ALTER|INDEX|ALL PRIVILEGES)"; then
    mariadb --protocol=socket <<SQL
REVOKE ALL PRIVILEGES, GRANT OPTION FROM '${DB_USER}'@'localhost';
GRANT SELECT, INSERT ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
    changed "runtime database grants"
else
    unchanged "runtime database grants"
fi

# ------------------------------------------------------------
# 6. Canonical schema: apply only when behind.
# ------------------------------------------------------------
echo "[6/9] Checking LMTS schema version..."
HAS_VERSION_TABLE="$(mariadb --protocol=socket "${DB_NAME}" -Nse "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='${DB_NAME}' AND TABLE_NAME='lmts_schema_version';")"
CURRENT_SCHEMA_VERSION=0
if [[ "${HAS_VERSION_TABLE}" == "1" ]]; then
    CURRENT_SCHEMA_VERSION="$(mariadb --protocol=socket "${DB_NAME}" -Nse "SELECT COALESCE(MAX(schema_version),0) FROM lmts_schema_version WHERE component='result_server';")"
fi
if (( CURRENT_SCHEMA_VERSION > SCHEMA_VERSION )); then
    echo "ERROR: installed result_server schema v${CURRENT_SCHEMA_VERSION} is newer than this installer supports (v${SCHEMA_VERSION})."
    exit 1
fi
if (( CURRENT_SCHEMA_VERSION < SCHEMA_VERSION )); then
    mariadb --protocol=socket "${DB_NAME}" < "${SCHEMA_FILE}"
    changed "LMTS schema v${CURRENT_SCHEMA_VERSION} -> v${SCHEMA_VERSION}"
else
    unchanged "LMTS schema v${SCHEMA_VERSION}"
fi

# ------------------------------------------------------------
# 7. Runtime configuration and user settings.
# ------------------------------------------------------------
echo "[7/9] Converging runtime configuration..."
if write_if_changed "${LMTS_CONFIG}/db.php" 640 root www-data <<PHP
<?php

return [
    'dsn' => 'mysql:host=${DB_HOST};dbname=${DB_NAME};charset=utf8mb4',
    'user' => '${DB_USER}',
    'password' => '${DB_PASSWORD}',
    'publish_key' => '${PUBLISH_KEY}',
];
PHP
then
    changed "runtime database config"
else
    unchanged "runtime database config"
fi
chmod 750 "${LMTS_CONFIG}"

mkdir -p "${SETTINGS_DIR}"
SETTINGS_CHANGED="$(DB_HOST="${DB_HOST}" DB_NAME="${DB_NAME}" DB_USER="${DB_USER}" DB_PASSWORD="${DB_PASSWORD}" PUBLISH_KEY="${PUBLISH_KEY}" SETTINGS_FILE="${SETTINGS_FILE}" python3 <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ['SETTINGS_FILE'])
try:
    current = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
except (OSError, ValueError, TypeError):
    current = {}
if not isinstance(current, dict):
    current = {}
desired = dict(current)
desired['schema_version'] = 2
desired.setdefault('output_folder', 'exports')
desired['mysql'] = {
    'host': os.environ['DB_HOST'],
    'database': os.environ['DB_NAME'],
    'username': os.environ['DB_USER'],
    'password': os.environ['DB_PASSWORD'],
    'publish_key': os.environ['PUBLISH_KEY'],
}
if current == desired:
    print('0')
else:
    temp = path.with_suffix(path.suffix + '.bootstrap-tmp')
    temp.write_text(json.dumps(desired, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(path)
    print('1')
PY
)"
chown -R "${CALLER_USER}:${CALLER_USER}" "${SETTINGS_DIR}"
chmod 700 "${SETTINGS_DIR}"
chmod 600 "${SETTINGS_FILE}"
if [[ "${SETTINGS_CHANGED}" == "1" ]]; then
    changed "LMTS user settings"
else
    unchanged "LMTS user settings"
fi

# ------------------------------------------------------------
# 8. Apache: restart only when configuration changed.
# ------------------------------------------------------------
echo "[8/9] Converging Apache host..."
APACHE_RESTART_REQUIRED=0
if write_if_changed "${APACHE_SITE}" 644 root root <<EOF
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
    Alias /benchmark/ ${LMTS_WEB}/
    <Directory ${LMTS_WEB}>
        Options FollowSymLinks
        AllowOverride None
        Require all granted
        DirectoryIndex index.html index.php
    </Directory>

    <Directory ${LMTS_CONFIG}>
        Require all denied
    </Directory>

    ErrorLog \${APACHE_LOG_DIR}/aigm-error.log
    CustomLog \${APACHE_LOG_DIR}/aigm-access.log combined
</VirtualHost>
EOF
then
    APACHE_RESTART_REQUIRED=1
    changed "Apache site configuration"
else
    unchanged "Apache site configuration"
fi

if [[ -e /etc/apache2/sites-enabled/000-default.conf ]]; then
    a2dissite 000-default.conf >/dev/null
    APACHE_RESTART_REQUIRED=1
    changed "disabled Apache default site"
fi
if [[ ! -e /etc/apache2/sites-enabled/000-aigm.conf ]]; then
    a2ensite 000-aigm.conf >/dev/null
    APACHE_RESTART_REQUIRED=1
    changed "enabled LMTS Apache site"
fi
apache2ctl configtest
if ! service_enabled apache2; then
    systemctl enable apache2
    changed "enabled Apache service"
fi
if service_active apache2; then
    if (( APACHE_RESTART_REQUIRED || SYSTEMD_RELOAD_REQUIRED )); then
        systemctl restart apache2
        restarted "Apache"
    else
        unchanged "Apache service already active"
    fi
else
    systemctl start apache2
    restarted "Apache started"
fi

setfacl -R -m "u:${CALLER_USER}:rwX" "${LMTS_WEB}"
find "${LMTS_WEB}" -type d -exec setfacl -m "d:u:${CALLER_USER}:rwx" {} \;

# ------------------------------------------------------------
# 9. Verification and summary.
# ------------------------------------------------------------
echo "[9/9] Verifying converged state..."
VERIFIED_SCHEMA="$(mariadb --protocol=socket "${DB_NAME}" -Nse "SELECT schema_version FROM lmts_schema_version WHERE component='result_server';")"
if [[ "${VERIFIED_SCHEMA}" != "${SCHEMA_VERSION}" ]]; then
    echo "ERROR: expected result_server schema v${SCHEMA_VERSION}, found v${VERIFIED_SCHEMA:-none}."
    exit 1
fi
if ! MYSQL_PWD="${DB_PASSWORD}" mariadb --protocol=tcp --host=127.0.0.1 --user="${DB_USER}" "${DB_NAME}" -Nse 'SELECT 1;' >/dev/null 2>&1; then
    echo "ERROR: LMTS runtime database account cannot connect after bootstrap."
    exit 1
fi

cat <<EOF

LMTS privileged bootstrap complete.

Database : ${DB_NAME}
User     : ${DB_USER}
Host     : ${DB_HOST}
Schema   : v${SCHEMA_VERSION}
Settings : ${SETTINGS_FILE}
Web root : ${LMTS_WEB}

Convergence summary:
  installed : ${INSTALLED}
  changed   : ${CHANGED}
  restarted : ${RESTARTED}
  unchanged : ${UNCHANGED}

Secrets remain in:
  ${SECRETS_FILE}
  ${SETTINGS_FILE}
  ${LMTS_CONFIG}/db.php

Secrets are not printed to stdout.
A second run checks the current state and only applies necessary changes.
For an existing local or remote database, use TUI -> MySQL -> Install schema instead.
EOF
