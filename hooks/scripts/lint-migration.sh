#!/usr/bin/env bash
# Requires Python 3.11+; see launch.sh for interpreter selection.
here="${BASH_SOURCE[0]%/*}"; [ "$here" = "${BASH_SOURCE[0]}" ] && here=.
exec "$BASH" "$here/launch.sh" lint-migration
