#!/usr/bin/env bash
# Launch the cyberdeck dashboard from this checkout.
set -euo pipefail
cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
  exec uv run cyberdeck "$@"
fi

# Fall back to a local virtualenv (handy right after a manual `pip install -e .`).
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m cyberdeck "$@"
fi

echo "uv not found. Install it first: brew install uv" >&2
exit 1
