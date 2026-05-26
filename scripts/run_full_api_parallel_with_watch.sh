#!/usr/bin/env bash
set -euo pipefail

exec python scripts/full_api_parallel_runner.py "$@"
