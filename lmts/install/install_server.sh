#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# LMTS Results Server bootstrap
# Debian 13
#
# - MariaDB data -> /home/lmts/mysql
# - Apache/PHP
# - Web root -> /home/www
# - Benchmark -> http://HOST/benchmark/
# - Future URL -> http://aigm.fi/benchmark/
# - LMTS database + minimal result schema
# - WebGUI checkout
# ============================================================

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root:"
    echo "  sudo $0"
    exit 1
fi

DB_NAME="lmts"
DB_USER="lmts"
WEB_EDITOR_USER="salanimi"

MYSQL_DATADIR="/home/lmts/mysql"

WWW_ROOT="/home/www"
AIGM_ROOT="${WWW_ROOT}/aigm.fi"
AIGM_PUBLIC="${AIGM_ROOT}/public"

LMTS_WEB="${WWW_ROOT}/lmts"
LMTS_PUBLIC="${LMTS_WEB}/public"
LMTS_CONFIG="${LMTS_WEB}/config"
WEBGUI_DIR="${LMTS_WEB}/WebGUI"

WEBGUI_REPO="https://github.com/Th3Hypn0tist/WebGUI.git"


APACHE_SITE="/etc/apache2/sites-available/000-aigm.conf"
MYSQL_CONFIG="/etc/mysql/mariadb.conf.d/99-lmts-datadir.cnf"

echo
echo "============================================================"
echo " LMTS server setup"
echo "============================================================"
echo

# ------------------------------------------------------------
# Packages
# ------------------------------------------------------------

echo "[1/11] Installing packages..."

export DEBIAN_FRONTEND=noninteractive

apt-get update

apt-get install -y \
    apache2 \
    mariadb-server \
    mariadb-client \
    php \
    libapache2-mod-php \
    php-mysql \
    git \
    rsync \
    openssl \
    curl \
    acl

# ------------------------------------------------------------
# Directories
# ------------------------------------------------------------

echo "[2/11] Creating /home data structure..."

if ! id "${WEB_EDITOR_USER}" >/dev/null 2>&1; then
    echo "ERROR: Unix user '${WEB_EDITOR_USER}' does not exist."
    exit 1
fi

mkdir -p \
    "${MYSQL_DATADIR}" \
    "${AIGM_PUBLIC}" \
    "${LMTS_PUBLIC}" \
    "${LMTS_CONFIG}"

chmod a+x /home
chmod 755 "${WWW_ROOT}"
chmod 755 "${AIGM_ROOT}"
chmod 755 "${AIGM_PUBLIC}"
chmod 755 "${LMTS_WEB}"
chmod 755 "${LMTS_PUBLIC}"

chown root:root /home/lmts
chmod 755 /home/lmts

# ------------------------------------------------------------
# MariaDB -> /home
# ------------------------------------------------------------

echo "[3/11] Moving MariaDB data to ${MYSQL_DATADIR}..."

systemctl stop mariadb

MIGRATED_MYSQL=0

if [[ ! -d "${MYSQL_DATADIR}/mysql" ]]; then

    if [[ ! -d /var/lib/mysql/mysql ]]; then
        echo "ERROR: /var/lib/mysql does not contain an initialized MariaDB database."
        exit 1
    fi

    rsync -aH --numeric-ids \
        /var/lib/mysql/ \
        "${MYSQL_DATADIR}/"

    MIGRATED_MYSQL=1
else
    echo "MariaDB data already exists in ${MYSQL_DATADIR}; migration skipped."
fi

chown -R mysql:mysql "${MYSQL_DATADIR}"
chmod 750 "${MYSQL_DATADIR}"

cat > "${MYSQL_CONFIG}" <<EOF
[mysqld]

datadir=${MYSQL_DATADIR}

# Database is only consumed locally by PHP.
bind-address=127.0.0.1
EOF

# ------------------------------------------------------------
# systemd: MariaDB must be allowed to access /home
# ------------------------------------------------------------

echo "[4/11] Configuring systemd permissions for /home..."

mkdir -p /etc/systemd/system/mariadb.service.d

cat > /etc/systemd/system/mariadb.service.d/lmts-home.conf <<EOF
[Service]
ProtectHome=false
ReadWritePaths=${MYSQL_DATADIR}
EOF

# Apache also needs to read /home/www.
mkdir -p /etc/systemd/system/apache2.service.d

cat > /etc/systemd/system/apache2.service.d/lmts-home.conf <<EOF
[Service]
ProtectHome=false
EOF

systemctl daemon-reload

# ------------------------------------------------------------
# AppArmor if present
# ------------------------------------------------------------

echo "[5/11] Checking AppArmor..."

configure_apparmor_profile() {
    local profile="$1"
    local local_file="$2"

    if [[ -f "${profile}" ]]; then
        mkdir -p "$(dirname "${local_file}")"

        touch "${local_file}"

        if ! grep -Fq "${MYSQL_DATADIR}/" "${local_file}" 2>/dev/null; then
            cat >> "${local_file}" <<EOF

# LMTS MariaDB datadir
${MYSQL_DATADIR}/ r,
${MYSQL_DATADIR}/** rwk,
EOF
        fi

        if command -v apparmor_parser >/dev/null 2>&1; then
            apparmor_parser -r "${profile}" || true
        fi
    fi
}

configure_apparmor_profile \
    "/etc/apparmor.d/mariadbd" \
    "/etc/apparmor.d/local/mariadbd"

# ------------------------------------------------------------
# Start MariaDB and verify new datadir
# ------------------------------------------------------------

echo "[6/11] Starting MariaDB..."

systemctl enable mariadb
systemctl restart mariadb

for attempt in {1..20}; do
    if mariadb-admin --protocol=socket ping >/dev/null 2>&1; then
        break
    fi

    sleep 1
done

if ! mariadb-admin --protocol=socket ping >/dev/null 2>&1; then
    echo
    echo "ERROR: MariaDB failed to start."
    echo
    systemctl status mariadb --no-pager || true
    journalctl -u mariadb -n 100 --no-pager || true
    exit 1
fi

ACTIVE_DATADIR="$(
    mariadb --protocol=socket -Nse \
        "SELECT @@datadir;" 2>/dev/null |
    head -n1
)"

echo "MariaDB active datadir: ${ACTIVE_DATADIR}"

if [[ "${ACTIVE_DATADIR%/}" != "${MYSQL_DATADIR%/}" ]]; then
    echo "ERROR: MariaDB is not using ${MYSQL_DATADIR}"
    exit 1
fi

# Only purge old copy after MariaDB has successfully booted from /home.
if [[ "${MIGRATED_MYSQL}" -eq 1 ]]; then
    echo "Removing old /var/lib/mysql data after successful migration..."

    find /var/lib/mysql \
        -mindepth 1 \
        -maxdepth 1 \
        -exec rm -rf -- {} +

    chown mysql:mysql /var/lib/mysql
fi

# ------------------------------------------------------------
# LMTS database
# ------------------------------------------------------------

echo "[7/11] Creating LMTS database..."

mariadb --protocol=socket <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost'
    IDENTIFIED BY 'lmts';

ALTER USER '${DB_USER}'@'localhost'
    IDENTIFIED BY 'lmts';

GRANT SELECT, INSERT, UPDATE, DELETE
    ON \`${DB_NAME}\`.*
    TO '${DB_USER}'@'localhost';

FLUSH PRIVILEGES;

USE \`${DB_NAME}\`;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SQL

# ------------------------------------------------------------
# PHP database config outside public tree
# ------------------------------------------------------------

cat > "${LMTS_CONFIG}/db.php" <<PHP
<?php

return [
    'dsn' => 'mysql:host=localhost;dbname=${DB_NAME};charset=utf8mb4',
    'user' => '${DB_USER}',
    'password' => 'lmts',
    'publish_key' => 'lmts',
];
PHP

chown root:www-data "${LMTS_CONFIG}/db.php"
chmod 640 "${LMTS_CONFIG}/db.php"
chmod 750 "${LMTS_CONFIG}"

# ------------------------------------------------------------
# WebGUI
# ------------------------------------------------------------

echo "[8/11] Installing WebGUI..."

if [[ -d "${WEBGUI_DIR}/.git" ]]; then

    git -C "${WEBGUI_DIR}" pull --ff-only || \
        echo "WARNING: WebGUI update failed; existing checkout retained."

elif [[ ! -e "${WEBGUI_DIR}" ]]; then

    if ! git clone "${WEBGUI_REPO}" "${WEBGUI_DIR}"; then
        echo "WARNING: Could not clone WebGUI."
        echo "The rest of the LMTS server will still be configured."
    fi

else
    echo "WARNING: ${WEBGUI_DIR} exists but is not a Git repository."
fi

if [[ -d "${WEBGUI_DIR}" ]]; then
    chown -R root:www-data "${WEBGUI_DIR}"
    chmod -R g+rX "${WEBGUI_DIR}"
fi

# ------------------------------------------------------------
# Web root permissions
# ------------------------------------------------------------

echo "[9/11] Preparing LMTS web root..."

chown -R root:www-data "${LMTS_WEB}"
find "${LMTS_WEB}" -type d -exec chmod 755 {} \;
find "${LMTS_WEB}" -type f -exec chmod 644 {} \;

# Simple placeholder for future aigm.fi root.
if [[ ! -f "${AIGM_PUBLIC}/index.html" ]]; then
    cat > "${AIGM_PUBLIC}/index.html" <<'HTML'
<!doctype html>
<html>
<head><meta charset="utf-8"><title>aigm.fi</title></head>
<body><h1>aigm.fi</h1></body>
</html>
HTML
fi

chown -R root:www-data "${AIGM_ROOT}"
find "${AIGM_ROOT}" -type d -exec chmod 755 {} \;
find "${AIGM_ROOT}" -type f -exec chmod 644 {} \;

# Human editor access, including future files/directories.
setfacl -R -m "u:${WEB_EDITOR_USER}:rwX" "${WWW_ROOT}"
find "${WWW_ROOT}" -type d -exec setfacl -m "d:u:${WEB_EDITOR_USER}:rwx" {} \;

# ------------------------------------------------------------
# Apache
# ------------------------------------------------------------

echo "[10/11] Configuring Apache port 80..."

if ! grep -Eq '^[[:space:]]*Listen[[:space:]]+80([[:space:]]|$)' \
    /etc/apache2/ports.conf
then
    echo "Listen 80" >> /etc/apache2/ports.conf
fi

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

    Alias /benchmark/WebGUI/ ${WEBGUI_DIR}/
    <Directory ${WEBGUI_DIR}>
        Options FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    Alias /benchmark/ ${LMTS_PUBLIC}/

    <Directory ${LMTS_PUBLIC}>
        Options FollowSymLinks
        AllowOverride None
        Require all granted
        DirectoryIndex index.php
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

# ------------------------------------------------------------
# Firewall if one happens to be active
# ------------------------------------------------------------

echo "[11/11] Checking firewall..."

if command -v ufw >/dev/null 2>&1; then
    if ufw status | grep -q "Status: active"; then
        ufw allow 80/tcp
    fi
fi

if command -v firewall-cmd >/dev/null 2>&1; then
    if firewall-cmd --state >/dev/null 2>&1; then
        firewall-cmd --permanent --add-service=http
        firewall-cmd --reload
    fi
fi

# ------------------------------------------------------------
# Final checks
# ------------------------------------------------------------

echo
echo "============================================================"
echo " LMTS setup complete"
echo "============================================================"
echo

echo "MariaDB:"
echo "  database : ${DB_NAME}"
echo "  user     : ${DB_USER}"
echo "  datadir  : ${MYSQL_DATADIR}"
echo "  password : lmts"
echo

echo "Web:"
echo "  root      : ${AIGM_PUBLIC}"
echo "  benchmark : ${LMTS_PUBLIC}"
echo "  WebGUI    : ${WEBGUI_DIR}"
echo "  editor    : ${WEB_EDITOR_USER} (ACL write access to ${WWW_ROOT})"
echo

echo "Apache:"
echo "  port      : 80"
echo "  future    : http://aigm.fi/benchmark/"
echo

IPS="$(hostname -I 2>/dev/null || true)"

for IP in ${IPS}; do
    case "${IP}" in
        *:*)
            ;;
        *)
            echo "  current   : http://${IP}/benchmark/"
            ;;
    esac
done

echo
echo "Service status:"
systemctl --no-pager --full status mariadb | sed -n '1,8p' || true
echo
systemctl --no-pager --full status apache2 | sed -n '1,8p' || true
echo

echo "DB credentials: lmts:lmts (localhost only)"
echo
