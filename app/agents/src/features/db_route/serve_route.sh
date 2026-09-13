#!/usr/bin/env bash
# Run serve_route.py with its three dependencies in a throwaway uv environment (no project install).
# Arguments pass through: --profile, --tag, --port, --data (see serve_route.py).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec uv run --no-project --with pandas --with pyarrow --with numpy python "$HERE/serve_route.py" "$@"
