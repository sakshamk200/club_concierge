#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# One-command verification of the DB stage against the configured DATABASE_URL
# (hosted Supabase by default — see backend/.env). No Docker required.
#
# Run from /backend:   bash scripts/verify_db.sh
#
# Applies all migrations, then runs the full pytest suite including the live
# asyncpg integration tests that round-trip every repository.
# -----------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."

PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY=".venv/bin/python"

echo "==> Applying migrations to DATABASE_URL..."
"$PY" scripts/apply_migrations.py

echo "==> Running full test suite (unit + live DB integration)..."
"$PY" -m pytest -v

echo "==> Done. All green => DB stage verified end-to-end."
