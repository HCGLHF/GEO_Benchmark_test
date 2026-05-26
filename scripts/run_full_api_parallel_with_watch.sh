#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"
exec "$PYTHON_BIN" scripts/full_api_parallel_runner.py "$@"
