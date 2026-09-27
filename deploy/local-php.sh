#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

REPORT_SOURCE="${ROOT_DIR}/php/"
BENCHMARK_SOURCE="${ROOT_DIR}/php/visualizer/"

REPORT_ROOT="${LMTS_LOCAL_REPORT_ROOT:-/home/www/lmts-report}"
BENCHMARK_ROOT="${LMTS_LOCAL_BENCHMARK_ROOT:-/home/www/lmts}"
SHARED_CONFIG="${LMTS_LOCAL_SHARED_CONFIG:-/home/www/config.php}"

usage() {
  cat <<'EOF'
Usage:
  bash deploy/local-php.sh reporting
  bash deploy/local-php.sh benchmark
  bash deploy/local-php.sh all

Environment overrides:
  LMTS_LOCAL_REPORT_ROOT
  LMTS_LOCAL_BENCHMARK_ROOT
  LMTS_LOCAL_SHARED_CONFIG
EOF
}

require_tools() {
  command -v rsync >/dev/null 2>&1 || {
    echo "ERROR: rsync is required" >&2
    exit 1
  }
  command -v php >/dev/null 2>&1 || {
    echo "ERROR: php CLI is required" >&2
    exit 1
  }
  command -v sudo >/dev/null 2>&1 || {
    echo "ERROR: sudo is required" >&2
    exit 1
  }
}

php_lint_tree() {
  local source="$1"
  local failed=0

  while IFS= read -r -d '' file; do
    if ! php -l "$file" >/dev/null; then
      failed=1
    fi
  done < <(find "$source" -type f -name '*.php' -print0)

  if [[ "$failed" -ne 0 ]]; then
    echo "ERROR: PHP lint failed" >&2
    exit 1
  fi
}

fix_permissions() {
  local target="$1"
  sudo chown -R root:www-data "$target"
  sudo find "$target" -type d -exec chmod 755 {} +
  sudo find "$target" -type f -exec chmod 644 {} +
}

deploy_reporting() {
  echo "==> LMTS local Reporting"
  echo "    source: ${REPORT_SOURCE}"
  echo "    target: ${REPORT_ROOT}/"

  php_lint_tree "$REPORT_SOURCE"
  sudo mkdir -p "$REPORT_ROOT"

  sudo rsync -a --delete \
    --exclude '/visualizer/' \
    --exclude '/config.php' \
    "$REPORT_SOURCE" "$REPORT_ROOT/"

  fix_permissions "$REPORT_ROOT"

  if [[ ! -f "$REPORT_ROOT/config.php" ]]; then
    echo "ERROR: reporting config missing: $REPORT_ROOT/config.php" >&2
    echo "Create it from php/config.example.php; deploy intentionally does not own secrets." >&2
    exit 1
  fi

  echo "    OK"
}

deploy_benchmark() {
  echo "==> LMTS local Benchmark"
  echo "    source: ${BENCHMARK_SOURCE}"
  echo "    target: ${BENCHMARK_ROOT}/"

  php_lint_tree "$BENCHMARK_SOURCE"

  if [[ ! -f "$SHARED_CONFIG" ]]; then
    echo "ERROR: benchmark shared config missing: $SHARED_CONFIG" >&2
    echo "php/visualizer/api/*.php expects the host-owned shared config there." >&2
    exit 1
  fi

  sudo mkdir -p "$BENCHMARK_ROOT"
  sudo rsync -a --delete "$BENCHMARK_SOURCE" "$BENCHMARK_ROOT/"
  fix_permissions "$BENCHMARK_ROOT"

  echo "    OK"
}

main() {
  require_tools
  sudo -v

  case "${1:-all}" in
    reporting)
      deploy_reporting
      ;;
    benchmark)
      deploy_benchmark
      ;;
    all)
      deploy_reporting
      deploy_benchmark
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
