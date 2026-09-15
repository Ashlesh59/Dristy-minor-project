#!/usr/bin/env bash
# scripts/test_backend.sh
# Cross-platform Bash test launcher for InvestIQ Phase 0

set -e

# 1. Locate repository root relative to script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
DEV_DB_PATH="$BACKEND_DIR/database/investiq.db"

echo "=========================================================="
echo "  InvestIQ Phase 0: Isolated Backend Test Runner (Bash)"
echo "=========================================================="
echo "Repository Root: $REPO_ROOT"
echo "Backend Dir:     $BACKEND_DIR"

# 2. Locate Python executable
PYTHON_EXE=""
if [ -f "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_EXE="$REPO_ROOT/.venv/bin/python"
elif [ -f "$REPO_ROOT/venv/bin/python" ]; then
    PYTHON_EXE="$REPO_ROOT/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_EXE="$(command -v python3)"
elif command -v python &>/dev/null; then
    PYTHON_EXE="$(command -v python)"
else
    echo "Error: Python executable not found." >&2
    exit 1
fi

echo "Python Executable: $PYTHON_EXE"

# 3. Development Database Integrity Check (Pre-Test)
PRE_HASH=""
PRE_SIZE=""
if [ -f "$DEV_DB_PATH" ]; then
    if command -v sha256sum &>/dev/null; then
        PRE_HASH="$(sha256sum "$DEV_DB_PATH" | awk '{print $1}')"
    elif command -v shasum &>/dev/null; then
        PRE_HASH="$(shasum -a 256 "$DEV_DB_PATH" | awk '{print $1}')"
    fi
    PRE_SIZE="$(wc -c < "$DEV_DB_PATH" | tr -d ' ')"
    echo "Pre-Test DB Hash: $PRE_HASH (Size: $PRE_SIZE bytes)"
else
    echo "Development database does not exist yet (clean slate)."
fi

# 4. Set Test Sentinel and Environment
export INVESTIQ_TEST_RUN="1"
export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"

echo ""
echo "Running test suite in backend directory..."

cd "$BACKEND_DIR"
set +e
"$PYTHON_EXE" -m unittest discover tests
TEST_EXIT_CODE=$?
set -e
cd "$REPO_ROOT"
unset INVESTIQ_TEST_RUN

# 5. Development Database Integrity Check (Post-Test)
echo ""
echo "Verifying development database integrity..."
if [ -n "$PRE_HASH" ]; then
    if [ ! -f "$DEV_DB_PATH" ]; then
        echo "CRITICAL SAFETY FAILURE: Development database was deleted during test run!" >&2
        exit 1
    fi

    POST_HASH=""
    if command -v sha256sum &>/dev/null; then
        POST_HASH="$(sha256sum "$DEV_DB_PATH" | awk '{print $1}')"
    elif command -v shasum &>/dev/null; then
        POST_HASH="$(shasum -a 256 "$DEV_DB_PATH" | awk '{print $1}')"
    fi
    POST_SIZE="$(wc -c < "$DEV_DB_PATH" | tr -d ' ')"
    echo "Post-Test DB Hash: $POST_HASH (Size: $POST_SIZE bytes)"

    if [ "$PRE_HASH" != "$POST_HASH" ] || [ "$PRE_SIZE" != "$POST_SIZE" ]; then
        echo "CRITICAL SAFETY FAILURE: Development database ($DEV_DB_PATH) was modified during test run!" >&2
        exit 1
    fi
    echo "SUCCESS: Development database remained 100% untouched and unchanged."
fi

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "All automated tests passed successfully."
else
    echo "Test suite failed with exit code $TEST_EXIT_CODE" >&2
fi

exit $TEST_EXIT_CODE
