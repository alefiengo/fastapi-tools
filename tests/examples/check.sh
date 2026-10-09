#!/usr/bin/env bash
set -euo pipefail
fixture_dir="$(cd "$(dirname "$0")" && pwd)"
exec "${EXAMPLES_PYTHON:-python3}" -m pytest "$fixture_dir/test_lifecycle.py" -q "$@"
