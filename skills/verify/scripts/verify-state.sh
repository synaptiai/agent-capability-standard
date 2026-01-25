#!/bin/bash
# verify-state.sh - Automated state verification for the verify skill
# Usage: ./verify-state.sh [--git] [--files] [--tests] [--all]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="${SCRIPT_DIR}/../.verification-report.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Initialize results
declare -A RESULTS
OVERALL_PASS=true

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    RESULTS["$1"]="PASS"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1: $2"
    RESULTS["$1"]="FAIL: $2"
    OVERALL_PASS=false
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check 1: Git state verification
verify_git() {
    echo "=== Git State Verification ==="

    if ! command -v git &> /dev/null; then
        log_warn "Git not available, skipping git checks"
        return
    fi

    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        log_warn "Not a git repository, skipping git checks"
        return
    fi

    # Check for uncommitted changes
    if git diff --quiet && git diff --cached --quiet; then
        log_pass "No uncommitted changes"
    else
        CHANGES=$(git status --short | wc -l | tr -d ' ')
        log_warn "Found $CHANGES uncommitted changes"
    fi

    # Check branch
    BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")
    echo "  Current branch: $BRANCH"

    # Check last commit
    LAST_COMMIT=$(git log -1 --format="%h %s" 2>/dev/null || echo "none")
    echo "  Last commit: $LAST_COMMIT"
}

# Check 2: File integrity verification
verify_files() {
    echo ""
    echo "=== File Integrity Verification ==="

    local target_dir="${1:-.}"

    # Check for expected files
    if [[ -f "${target_dir}/package.json" ]]; then
        log_pass "package.json exists"
    fi

    if [[ -f "${target_dir}/CLAUDE.md" ]]; then
        log_pass "CLAUDE.md exists"
    fi

    # Check for broken symlinks
    BROKEN_LINKS=$(find "$target_dir" -maxdepth 3 -xtype l 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$BROKEN_LINKS" -eq 0 ]]; then
        log_pass "No broken symlinks found"
    else
        log_fail "Broken symlinks" "Found $BROKEN_LINKS broken symlinks"
    fi

    # Check for empty files that shouldn't be empty
    EMPTY_FILES=$(find "$target_dir" -maxdepth 3 -type f -empty -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$EMPTY_FILES" -eq 0 ]]; then
        log_pass "No empty markdown files"
    else
        log_warn "Found $EMPTY_FILES empty markdown files"
    fi
}

# Check 3: Test execution
verify_tests() {
    echo ""
    echo "=== Test Verification ==="

    # Detect test framework and run
    if [[ -f "package.json" ]]; then
        if grep -q '"test"' package.json 2>/dev/null; then
            echo "  Detected npm test script"
            if npm test --if-present 2>/dev/null; then
                log_pass "npm tests passed"
            else
                log_fail "npm tests" "Tests failed or not configured"
            fi
        else
            log_warn "No npm test script found"
        fi
    elif [[ -f "pytest.ini" ]] || [[ -f "setup.py" ]]; then
        echo "  Detected Python project"
        if python -m pytest --quiet 2>/dev/null; then
            log_pass "pytest tests passed"
        else
            log_fail "pytest" "Tests failed or pytest not available"
        fi
    elif [[ -f "Gemfile" ]]; then
        echo "  Detected Ruby project"
        if bundle exec rspec --format progress 2>/dev/null; then
            log_pass "rspec tests passed"
        else
            log_fail "rspec" "Tests failed or rspec not available"
        fi
    else
        log_warn "No recognized test framework detected"
    fi
}

# Generate JSON report
generate_report() {
    echo ""
    echo "=== Generating Report ==="

    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local verdict="PASS"
    [[ "$OVERALL_PASS" = false ]] && verdict="FAIL"

    cat > "$OUTPUT_FILE" << EOF
{
  "verification_report": {
    "timestamp": "$timestamp",
    "verdict": "$verdict",
    "checks": {
EOF

    local first=true
    for key in "${!RESULTS[@]}"; do
        [[ "$first" = true ]] && first=false || echo "," >> "$OUTPUT_FILE"
        echo "      \"$key\": \"${RESULTS[$key]}\"" >> "$OUTPUT_FILE"
    done

    cat >> "$OUTPUT_FILE" << EOF
    }
  }
}
EOF

    echo "Report saved to: $OUTPUT_FILE"
}

# Main
main() {
    local run_git=false
    local run_files=false
    local run_tests=false

    # Parse arguments
    for arg in "$@"; do
        case $arg in
            --git) run_git=true ;;
            --files) run_files=true ;;
            --tests) run_tests=true ;;
            --all) run_git=true; run_files=true; run_tests=true ;;
            *) echo "Unknown option: $arg"; exit 1 ;;
        esac
    done

    # Default to all if no options specified
    if [[ "$run_git" = false ]] && [[ "$run_files" = false ]] && [[ "$run_tests" = false ]]; then
        run_git=true
        run_files=true
        run_tests=true
    fi

    echo "========================================"
    echo "  State Verification Script"
    echo "  $(date)"
    echo "========================================"

    [[ "$run_git" = true ]] && verify_git
    [[ "$run_files" = true ]] && verify_files "."
    [[ "$run_tests" = true ]] && verify_tests

    generate_report

    echo ""
    if [[ "$OVERALL_PASS" = true ]]; then
        echo -e "${GREEN}Overall: PASS${NC}"
        exit 0
    else
        echo -e "${RED}Overall: FAIL${NC}"
        exit 1
    fi
}

main "$@"
