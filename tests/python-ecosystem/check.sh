#!/usr/bin/env bash
set -euo pipefail
exec "${ECOSYSTEM_PYTHON:-python3}" "$(dirname "$0")/check.py" "$@"
