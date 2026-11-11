#!/usr/bin/env bash
# Starts hook-runtime.py with a Python 3.11+ interpreter, independent of the
# application's environment (same rule as the MCP server): FASTAPI_TOOLS_PYTHON
# when set, otherwise the first of python3, python3.14 ... python3.11 on PATH.
# No usable interpreter fails open with an explicit diagnostic.
set -uo pipefail
action="$1"
here="${BASH_SOURCE[0]%/*}"; [ "$here" = "${BASH_SOURCE[0]}" ] && here=.
here="$(cd "$here" && pwd)"
usable() {
  "$1" -I -S -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}
if [ -n "${FASTAPI_TOOLS_PYTHON:-}" ]; then
  candidates=("$FASTAPI_TOOLS_PYTHON")
else
  candidates=(python3 python3.14 python3.13 python3.12 python3.11)
fi
for candidate in "${candidates[@]}"; do
  if command -v "$candidate" >/dev/null 2>&1 && usable "$candidate"; then
    # -I ignores PYTHON* variables and the script directory, -S skips site and
    # .pth processing (the runtime uses only the standard library), for the
    # hook process only; build subprocesses receive the unchanged environment.
    exec "$candidate" -I -S "$here/hook-runtime.py" "$action"
  fi
done
if [ -n "${FASTAPI_TOOLS_PYTHON:-}" ]; then
  printf '%s\n' '{"systemMessage":"FastAPI hook skipped: FASTAPI_TOOLS_PYTHON is not a usable Python 3.11+ interpreter."}'
else
  printf '%s\n' '{"systemMessage":"FastAPI hook skipped: Python 3.11+ is required; checked python3, python3.14, python3.13, python3.12, python3.11. Set FASTAPI_TOOLS_PYTHON to a Python 3.11+ interpreter."}'
fi
exit 0
