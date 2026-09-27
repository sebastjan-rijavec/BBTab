#!/usr/bin/env bash
#
# run_the_damn_thing.sh — just launch BBTab already.
#
# Uses the project's virtualenv if it exists, otherwise falls back to the
# system python3 (the GTK/Adwaita bindings are system packages anyway).
# Any arguments are passed straight through to run.py, e.g.:
#
#     ./run_the_damn_thing.sh mysong.bbtab

set -euo pipefail

# Always run from the project root, wherever this script is called from.
cd "$(dirname "$(readlink -f "$0")")"

if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    echo "No .venv found — falling back to system python3." >&2
    PYTHON="python3"
fi

exec "$PYTHON" run.py "$@"
